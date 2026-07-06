"""视频管理 API：解析、列表、详情、删除。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
import asyncio

from app.core.database import get_db
from app.models.video import Video
from app.models.note import Note
from app.schemas.video import VideoResponse
from app.store.mock import MockStore

router = APIRouter(prefix="/videos", tags=["videos"])


class ParseResponse(BaseModel):
    video_id: str
    title: str
    uploader: str | None = None
    uploader_uid: str | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None
    bvid: str | None = None
    avid: int | None = None
    description: str | None = None
    is_playlist: bool = False
    playlist_title: str | None = None


class VideoParseRequest(BaseModel):
    url: str


class VideoProcessRequest(BaseModel):
    url: str
    quality: str = "1080p"
    transcriber: str = "auto"
    keep_video: bool = False


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/parse", response_model=ParseResponse)
async def parse_video(body: VideoParseRequest):
    """解析 B 站视频链接，返回元数据（BilibiliVideoProcessor 真实解析）。"""
    from app.processor.video_processor import BilibiliVideoProcessor
    from app.core.config import settings
    proc = BilibiliVideoProcessor(data_dir=settings.data_dir)
    result = await proc.parse(body.url)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "解析失败")
    meta = result.metadata
    return ParseResponse(
        video_id=meta.get("video_id", ""),
        title=meta.get("title", ""),
        uploader=meta.get("uploader"),
        uploader_uid=meta.get("uploader_uid"),
        duration_seconds=int(meta["duration_seconds"]) if meta.get("duration_seconds") else None,
        cover_url=meta.get("cover_url"),
        bvid=meta.get("bvid"),
        avid=int(meta["avid"]) if meta.get("avid") else None,
        description=meta.get("description"),
    )


@router.post("/process")
async def process_video(body: VideoProcessRequest, orchestrator=Depends(get_orchestrator)):
    """提交视频处理，返回 task_id，前端轮询进度。"""
    task = await orchestrator.start_task(body.url)
    return {"task_id": task.task_id, "video_id": task.video_id, "status": task.status.value}


@router.get("/")
def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(None),
    search: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Video)
    if status:
        q = q.filter(Video.status == status)
    if search:
        q = q.filter(Video.title.ilike(f"%{search}%"))
    total = q.count()
    items = q.order_by(Video.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [VideoResponse.model_validate(v).model_dump() for v in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    return video


@router.delete("/{video_id}")
async def delete_video(video_id: str, request: Request, db: Session = Depends(get_db)):
    # 取消正在运行的管线任务
    orch = getattr(request.app.state, "orchestrator", None)
    if orch:
        for tid, t in list(getattr(orch, "_tasks", {}).items()):
            if t.video_id == video_id:
                orch.cancel_task(tid)
                break
    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    freed = video.file_size or 0
    if video.video_path:
        p = Path(video.video_path)
        if p.exists():
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
    if video.audio_path:
        p = Path(video.audio_path)
        if p.exists():
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
    note = db.query(Note).filter(Note.video_id == video.id).first()
    deleted_chunks = 0
    if note:
        p = Path(note.file_path)
        if p.exists():
            p.unlink(missing_ok=True)
        deleted_chunks = note.total_chunks or 0
    db.delete(video)
    db.commit()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "deleted_video": True,
            "deleted_notes": bool(note),
            "deleted_chunks": deleted_chunks,
            "deleted_vectors": deleted_chunks,
            "freed_space_bytes": freed,
        },
    }
