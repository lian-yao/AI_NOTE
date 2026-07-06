"""任务管理 API：状态查询、日志、重试。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.task import Task as TaskModel
from app.models.task_log import TaskLog

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
                from pathlib import Path
                nr = db.query(Note).filter(Note.id == pipe_task.note_id).first()
                if nr and nr.file_path:
                    fp = Path(nr.file_path)
                    if fp.exists():
                        result = {"markdown": fp.read_text(encoding="utf-8")}
            return {
                "task_id": pipe_task.task_id,
                "video_id": pipe_task.video_id,
                "status": pipe_task.status.value,
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
            from app.models.note import Note
            nr = db.query(Note).filter(Note.video_id == video.id).first()
            if nr and nr.file_path:
                from pathlib import Path
                fp = Path(nr.file_path)
                if fp.exists():
                    result = {"markdown": fp.read_text(encoding="utf-8")}
        return {
            "task_id": task_id,
            "video_id": task_id,
            "status": "completed" if video.status in ("completed", "stored") else video.status,
            "progress": 100 if video.status in ("completed", "stored", "downloaded", "transcribed") else 0,
            "result": result,
        }
    # 3. 回退到 DB Task 记录
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


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
def retry_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败的任务才能重试")
    task.status = "pending"
    task.retry_count = (task.retry_count or 0) + 1
    task.error_message = None
    db.commit()
    return {"task_id": task.task_id, "status": task.status, "retry_count": task.retry_count}

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
    db.commit()
    return {"task_id": task_id, "status": "cancelled", "cancelled": cancelled_any}

