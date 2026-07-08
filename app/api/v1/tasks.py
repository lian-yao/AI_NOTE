"""任务管理 API：状态查询、日志、重试。"""
import json
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.paths import project_root
from app.models.task import Task as TaskModel
from app.models.task_log import TaskLog
from app.note.timeline import (
    build_timeline_sections_from_segments,
    extract_timeline_sections,
    timeline_sections_have_ranges,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _has_local_video_file(video) -> bool:
    video_path = getattr(video, "video_path", None)
    if not video_path:
        return False
    path = Path(video_path)
    if not path.is_absolute():
        path = Path(project_root()) / path
    return path.is_file()


def _snapshot_url(video, seconds: int | float | None) -> str:
    video_id = getattr(video, "video_id", "")
    if not video_id or not _has_local_video_file(video):
        return ""
    return f"/api/v1/videos/{quote(video_id, safe='')}/snapshot?time={max(0, int(seconds or 0))}"


def _read_note_markdown(db: Session, video_id: int | None) -> str:
    if not video_id:
        return ""
    from app.models.note import Note

    note = db.query(Note).filter(Note.video_id == video_id).first()
    if not note or not note.file_path:
        return ""
    path = Path(note.file_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_transcript(video) -> dict:
    paths = []
    for value in (getattr(video, "audio_path", None), getattr(video, "video_path", None)):
        if not value:
            continue
        path = Path(value)
        paths.append(path.parent / "transcription.json")
    video_id = getattr(video, "video_id", "")
    if video_id:
        paths.append(Path(project_root()) / "data" / "videos" / video_id / "transcription.json")

    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "full_text": data.get("full_text", ""),
                "language": data.get("language", "zh-CN"),
                "raw": data,
                "segments": data.get("segments", []),
            }
        except Exception:
            continue

    return {"full_text": "", "language": "zh-CN", "raw": None, "segments": []}


def _with_snapshot_urls(video, sections: list[dict]) -> list[dict]:
    for section in sections:
        if not section.get("screenshot_url"):
            section["screenshot_url"] = _snapshot_url(video, section.get("start_time"))
    return sections


def _read_timeline_sections(
    db: Session,
    video,
    markdown: str,
    transcript: dict | None = None,
) -> list[dict]:
    sections = extract_timeline_sections(markdown)
    if sections and timeline_sections_have_ranges(sections):
        return _with_snapshot_urls(video, sections)

    video_id = getattr(video, "id", None)
    if not video_id:
        return _with_snapshot_urls(
            video,
            build_timeline_sections_from_segments((transcript or {}).get("segments", []), sections),
        )

    from app.models.chunk import Chunk

    chunks = (
        db.query(Chunk)
        .filter(Chunk.video_id == video_id)
        .order_by(Chunk.chunk_index.asc(), Chunk.id.asc())
        .all()
    )
    items = []
    for index, chunk in enumerate(chunks):
        item = {
            "title": chunk.section_title or f"片段 {index + 1}",
            "start_time": chunk.start_time or 0,
            "end_time": chunk.end_time or 0,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
        }
        snapshot_url = _snapshot_url(video, chunk.start_time)
        if snapshot_url:
            item["screenshot_url"] = snapshot_url
        items.append(item)
    if timeline_sections_have_ranges(items):
        return _with_snapshot_urls(video, items)

    transcript_sections = build_timeline_sections_from_segments(
        (transcript or {}).get("segments", []),
        items or sections,
    )
    if transcript_sections:
        return _with_snapshot_urls(video, transcript_sections)

    return _with_snapshot_urls(video, items or sections)


def _audio_meta(video, chapters: list[dict] | None = None) -> dict:
    return {
        "cover_url": video.cover_url or "",
        "duration": video.duration_seconds or 0,
        "file_path": video.audio_path or "",
        "platform": "bilibili",
        "raw_info": {
            "uploader": video.uploader or "",
            "bvid": video.bvid or "",
            "avid": video.avid,
        },
        "title": video.title or video.url,
        "video_id": video.video_id,
        "source_url": video.url,
        "player_url": None,
        "embed_url": (
            f"https://player.bilibili.com/player.html?bvid={video.bvid}&page=1&high_quality=1&autoplay=0"
            if video.bvid else None
        ),
        "chapters": chapters or [],
    }


def _task_result(db: Session, video) -> dict | None:
    if not video:
        return None
    markdown = _read_note_markdown(db, video.id)
    if not markdown:
        return None
    transcript = _read_transcript(video)
    chapters = _read_timeline_sections(db, video, markdown, transcript)
    return {
        "markdown": markdown,
        "transcript": transcript,
        "audio_meta": _audio_meta(video, chapters),
    }


def _aggregate_stage_tasks(task_id: str, db: Session):
    stage_tasks = (
        db.query(TaskModel)
        .filter(TaskModel.task_id.like(f"{task_id}_%"))
        .order_by(TaskModel.created_at.asc(), TaskModel.id.asc())
        .all()
    )
    if not stage_tasks:
        return None

    from app.models.video import Video

    video = None
    for item in reversed(stage_tasks):
        if item.video_id:
            video = db.query(Video).filter(Video.id == item.video_id).first()
            if video:
                break

    cancelled = next((item for item in stage_tasks if item.status == "cancelled"), None)
    if cancelled:
        return {
            "task_id": task_id,
            "video_id": video.video_id if video else None,
            "status": "cancelled",
            "progress": cancelled.progress or 0,
            "message": cancelled.error_message or "任务已取消",
            "result": None,
        }

    failed = next((item for item in stage_tasks if item.status == "failed"), None)
    if failed:
        return {
            "task_id": task_id,
            "video_id": video.video_id if video else None,
            "status": "failed",
            "progress": failed.progress or 0,
            "message": failed.error_message or "任务处理失败",
            "result": None,
        }

    running = next((item for item in reversed(stage_tasks) if item.status in ("running", "pending", "retrying")), None)
    if running:
        return {
            "task_id": task_id,
            "video_id": video.video_id if video else None,
            "status": running.status,
            "progress": running.progress or 0,
            "message": "",
            "result": None,
        }

    store_done = any(item.type == "store" and item.status == "completed" for item in stage_tasks)
    generate_done = any(item.type == "generate" and item.status == "completed" for item in stage_tasks)
    if store_done or (generate_done and video and _read_note_markdown(db, video.id)):
        return {
            "task_id": task_id,
            "video_id": video.video_id if video else None,
            "status": "completed",
            "progress": 100,
            "message": "处理完成",
            "result": _task_result(db, video),
        }

    latest = stage_tasks[-1]
    if latest.status == "completed":
        return {
            "task_id": task_id,
            "video_id": video.video_id if video else None,
            "status": "failed",
            "progress": latest.progress or 0,
            "message": "任务处理中断，请重试",
            "result": None,
        }

    return {
        "task_id": task_id,
        "video_id": video.video_id if video else None,
        "status": latest.status,
        "progress": latest.progress or 0,
        "message": latest.error_message or "",
        "result": None,
    }


def _root_task_id(task_id: str) -> str:
    for suffix in ("_parse", "_download", "_transcribe", "_generate", "_store"):
        if task_id.endswith(suffix):
            return task_id[: -len(suffix)]
    return task_id


@router.get("/{task_id}")
def get_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    # 1. Check orchestrator in-memory tasks first (real-time status)
    orch = getattr(request.app.state, "orchestrator", None)
    if orch:
        pipe_task = orch.get_task(task_id)
        if pipe_task:
            result = None
            if pipe_task.status.value == "completed" and pipe_task.note_id:
                from app.models.note import Note
                from app.models.video import Video

                nr = db.query(Note).filter(Note.id == pipe_task.note_id).first()
                video = db.query(Video).filter(Video.id == nr.video_id).first() if nr else None
                result = _task_result(db, video)
            stage = pipe_task.current_stage.value if pipe_task.current_stage else None
            return {
                "task_id": pipe_task.task_id,
                "video_id": pipe_task.video_id,
                "status": pipe_task.status.value,
                "stage": stage,
                "progress": pipe_task.progress,
                "message": pipe_task.error or "",
                "result": result,
            }
    # 2. 支持 video_id 查询（返回笔记内容）
    from app.models.video import Video
    video = db.query(Video).filter(Video.video_id == task_id).first()
    if video:
        result = None
        if video.status in ("completed", "stored"):
            result = _task_result(db, video)
        return {
            "task_id": task_id,
            "video_id": task_id,
            "status": "completed" if video.status in ("completed", "stored") else video.status,
            "progress": 100 if video.status in ("completed", "stored", "downloaded", "transcribed") else 0,
            "result": result,
        }
    # 3. 回退到 DB Task 记录
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if task:
        return task

    # 4. 聚合 task_xxx_parse / task_xxx_download 等阶段记录。
    aggregated = _aggregate_stage_tasks(task_id, db)
    if aggregated:
        return aggregated

    raise HTTPException(status_code=404, detail="任务不存在")


@router.get("/{task_id}/logs")
def get_task_logs(
    task_id: str,
    level: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    q = db.query(TaskLog).filter(TaskLog.task_id == task_id)
    if level:
        q = q.filter(TaskLog.level == level.upper())
    total = q.count()
    items = q.order_by(TaskLog.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    root_task_id = _root_task_id(task_id)
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    stage_tasks = (
        db.query(TaskModel)
        .filter(TaskModel.task_id.like(f"{root_task_id}_%"))
        .order_by(TaskModel.created_at.asc(), TaskModel.id.asc())
        .all()
    )
    candidates = stage_tasks or ([task] if task else [])
    failed_tasks = [item for item in candidates if item and item.status == "failed"]
    if not failed_tasks:
        if not candidates:
            raise HTTPException(status_code=404, detail="任务不存在")
        raise HTTPException(status_code=400, detail="只有失败的任务才能重试")

    from app.models.video import Video

    video = None
    for item in reversed(candidates):
        if item and item.video_id:
            video = db.query(Video).filter(Video.id == item.video_id).first()
            if video:
                break
    if not video or not video.url:
        raise HTTPException(status_code=404, detail="任务关联视频不存在，无法重试")

    orch = getattr(request.app.state, "orchestrator", None)
    if not orch:
        raise HTTPException(status_code=503, detail="任务编排器未就绪")

    retry_count = 0
    for item in failed_tasks:
        item.status = "retrying"
        item.retry_count = (item.retry_count or 0) + 1
        item.error_message = None
        item.progress = 0
        retry_count = max(retry_count, item.retry_count or 0)
    db.commit()

    pipe_task = await orch.start_task(video.url, options={"client_task_id": root_task_id})
    return {"task_id": pipe_task.task_id, "status": pipe_task.status.value, "retry_count": retry_count}

@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    """取消正在进行的任务。"""
    # 1. 取消 orchestrator 内存任务
    orch = getattr(request.app.state, "orchestrator", None)
    cancelled_any = False
    if orch:
        cancelled_any = orch.cancel_task(task_id)
        if not cancelled_any:
            # 还可能是视频 ID 作为 task_id 传入
            try:
                for tid, t in list(orch._tasks.items()):
                    if t.video_id == task_id:
                        orch.cancel_task(tid)
                        cancelled_any = True
                        break
            except Exception:
                pass
    # 2. 更新 DB 任务记录
    tasks = db.query(TaskModel).filter(
        TaskModel.task_id.like(f"%{task_id}%"),
        TaskModel.status.in_(["pending", "running"])
    ).all()
    for t in tasks:
        t.status = "cancelled"
        t.error_message = "已被用户取消"
    # 3. 更新 Video 状态，避免 listVideos / backendVideoToTask 重新恢复任务
    if tasks:
        from app.models.video import Video
        video_ids = {t.video_id for t in tasks if t.video_id and t.video_id != 0}
        db.query(Video).filter(Video.id.in_(list(video_ids))).update({"status": "cancelled"}, synchronize_session="fetch")
    db.commit()
    return {"task_id": task_id, "status": "cancelled", "cancelled": cancelled_any}
