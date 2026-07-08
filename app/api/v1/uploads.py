"""本地文件上传 API。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.paths import project_path

router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus", ".wma",
    ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv",
    ".3gp", ".3g2",
}

_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


def _upload_dir() -> Path:
    p = project_path(settings.data_dir, "uploads")
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/videos")
async def upload_video(file: UploadFile = File(...)):
    """上传本地音视频文件，返回 file_id / filename / size_bytes / url。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    original_filename = file.filename.strip()
    suffix = Path(original_filename).suffix.lower()

    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}。支持的格式: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    file_id = uuid.uuid4().hex[:16]
    safe_filename = f"{file_id}{suffix}"
    dest_path = _upload_dir() / safe_filename

    total_bytes = 0
    try:
        with dest_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > _MAX_UPLOAD_BYTES:
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大，最大支持 {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}")

    if total_bytes == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="上传的文件为空")

    relative_path = Path(settings.data_dir, "uploads", safe_filename).as_posix()
    local_url = f"local://{relative_path}"

    return {
        "file_id": file_id,
        "filename": original_filename,
        "size_bytes": total_bytes,
        "url": local_url,
    }


@router.get("/videos/{file_id}/media")
async def stream_uploaded_file(file_id: str):
    """流式播放已上传的本地文件。"""
    upload_dir = _upload_dir()
    candidates = list(upload_dir.glob(f"{file_id}.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="文件不存在或已被清理")

    file_path = candidates[0]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或已被清理")

    suffix = file_path.suffix.lower()
    _mime_map = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".flac": "audio/flac", ".aac": "audio/aac", ".m4a": "audio/mp4",
        ".opus": "audio/opus",
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".mkv": "video/x-matroska",
        ".webm": "video/webm", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
        ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv",
    }
    media_type = _mime_map.get(suffix, "application/octet-stream")
    file_size = file_path.stat().st_size

    def iter_file():
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=media_type,
        headers={
            "content-length": str(file_size),
            "accept-ranges": "bytes",
            "content-disposition": f'inline; filename="{file_path.name}"',
        },
    )
