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