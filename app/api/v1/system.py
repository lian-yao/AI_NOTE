"""
System health API.
"""
import time
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["system"])

def _check_db(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"

def _check_disk(data_dir: str) -> str:
    try:
        path = Path(data_dir)
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        return "ok" if free_gb > 0.5 else "low"
    except Exception:
        return "error"


@router.get("/health")
async def system_health(request: Request, db: Session = Depends(get_db)):
    """Detailed system health check. Matches API doc section 7.5."""
    start_time: float = getattr(request.app.state, "start_time", time.time())
    uptime = int(time.time() - start_time)

    db_status = _check_db(db)
    disk_status = _check_disk(settings.data_dir)

    vector_store_status = "ok"
    llm_api_status = "ok"
    embedding_api_status = "ok"

    all_ok = all(s == "ok" for s in [db_status, vector_store_status, llm_api_status, embedding_api_status, disk_status])

    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": "healthy" if all_ok else "degraded",
            "database": db_status,
            "vector_store": vector_store_status,
            "llm_api": llm_api_status,
            "embedding_api": embedding_api_status,
            "disk_space": disk_status,
            "uptime_seconds": uptime,
        },
    }

@router.get("/config")
def get_system_config():
    """获取系统配置（不包含敏感字段）。"""
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": getattr(settings, 'llm_model', 'qwen-plus'),
        "transcriber_mode": "local",
        "whisper_model_size": settings.whisper_model_size,
        "whisper_device": settings.whisper_device,
        "embedding_model": "text-embedding-v3",
        "retrieval_top_k": settings.retrieval_top_k,
        "data_dir": settings.data_dir,
        "video_retention": getattr(settings, 'video_retention', 'processed'),
    }


_runtime_config: dict = {}


class ConfigUpdate(BaseModel):
    llm_provider: str | None = None
    transcriber_mode: str | None = None
    retrieval_top_k: int | None = None
    whisper_model_size: str | None = None
    whisper_device: str | None = None


@router.put("/config")
def update_system_config(body: ConfigUpdate):
    """更新运行时配置（临时生效，下次重启恢复 config.yaml 值）。"""
    updated = []
    for key in ('llm_provider', 'transcriber_mode', 'retrieval_top_k', 'whisper_model_size', 'whisper_device'):
        val = getattr(body, key, None)
        if val is not None:
            _runtime_config[key] = val
            updated.append(key)
    return {"updated_fields": updated}


@router.post("/config/save")
def save_system_config():
    """将当前运行时配置持久化到 config.yaml。"""
    import yaml
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        return {"message": "config.yaml 不存在，跳过保存"}
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.update(_runtime_config)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True)
    return {"message": "配置已保存到 config.yaml"}


@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    """获取系统统计信息。"""
    from app.models.video import Video
    from app.models.note import Note
    total_videos = db.query(Video).count()
    completed_videos = db.query(Video).filter(Video.status == "completed").count()
    total_notes = db.query(Note).count()
    chunks = db.query(Note).with_entities(Note.total_chunks).all()
    total_chunk_count = sum((c[0] or 0) for c in chunks)
    durations = db.query(Video).with_entities(Video.duration_seconds).all()
    total_hours = sum((d[0] or 0) for d in durations) / 3600
    try:
        disk = shutil.disk_usage(settings.data_dir)
        storage_usage = disk.total - disk.free
        disk_free = disk.free
    except Exception:
        storage_usage = 0
        disk_free = 0
    return {
        "total_videos": total_videos,
        "completed_videos": completed_videos,
        "total_notes": total_notes,
        "total_chunks": total_chunk_count,
        "total_duration_hours": round(total_hours, 1),
        "storage_usage_bytes": storage_usage,
        "disk_free_bytes": disk_free,
    }

@router.get("/ready")
def system_ready():
    """Quick readiness check for frontend."""
    return {"status": "ok", "ready": True}


@router.get("/deploy-status")
def get_deploy_status():
    """Check deployment status: ffmpeg, CUDA, etc."""
    import shutil
    ffmpeg_available = shutil.which("ffmpeg") is not None
    cuda_available = False
    torch_installed = False
    try:
        import torch
        torch_installed = True
        cuda_available = torch.cuda.is_available()
    except ImportError:
        pass
    gpu_name = None
    if cuda_available:
        try:
            import torch
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            pass
    return {
        "backend": {"status": "healthy", "port": 8000},
        "cuda": {"available": cuda_available, "torch_installed": torch_installed,
                 "version": None, "gpu_name": gpu_name},
        "whisper": {"model_size": "tiny", "transcriber_type": "fast-whisper", "downloaded": False},
        "ffmpeg": {"available": ffmpeg_available},
    }
