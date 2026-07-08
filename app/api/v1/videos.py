"""视频管理 API：解析、列表、详情、删除。"""
from __future__ import annotations

import asyncio
import mimetypes
import re
import subprocess
import time
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path

from app.core.database import get_db
from app.core.paths import project_root
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


class VideoPlayerRequest(BaseModel):
    url: str
    quality: str = "1080p"
    video_id: str | None = None


class VideoPlayerResponse(BaseModel):
    title: str
    source_url: str
    webpage_url: str | None = None
    stream_url: str | None = None
    local_stream_url: str | None = None
    embed_url: str | None = None
    cover_url: str | None = None
    duration_seconds: int | None = None
    format_id: str | None = None
    ext: str | None = None
    height: int | None = None
    is_proxy_stream: bool = True
    player_type: str = "embed"


class VideoProcessRequest(BaseModel):
    url: str
    quality: str = "1080p"
    transcriber: str = "auto"
    keep_video: bool = False
    provider_id: str | None = None
    model_name: str | None = None
    format: list[str] | None = None
    style: str | None = None
    extras: str | None = None
    video_understanding: bool = False
    video_interval: int = 6
    grid_size: list[int] | None = None
    platform: str | None = None
    task_id: str | None = None


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


_PLAYER_CACHE_TTL_SECONDS = 10 * 60
_PLAYER_CACHE: dict[str, tuple[float, dict]] = {}
_MEDIA_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mov", ".mkv"}
_BVID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")


def _is_supported_bilibili_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("bilibili.com") or host.endswith("b23.tv")


def _target_height(quality: str) -> int:
    value = (quality or "").lower()
    if "360" in value:
        return 360
    if "480" in value:
        return 480
    if "720" in value:
        return 720
    return 1080


def _video_local_stream_path(video_id: str) -> str:
    return f"/api/v1/videos/{quote(video_id, safe='')}/media"


def _resolve_local_video_path(video: Video | None) -> Path | None:
    if not video or not video.video_path:
        return None

    path = Path(video.video_path)
    if not path.is_absolute():
        path = project_root() / path

    try:
        path = path.resolve()
    except OSError:
        return None

    if not path.is_file() or path.suffix.lower() not in _MEDIA_EXTENSIONS:
        return None
    return path


def _extract_bvid(value: str | None) -> str | None:
    if not value:
        return None
    match = _BVID_PATTERN.search(value)
    return match.group(0) if match else None


def _find_video_for_player(
    db: Session,
    video_id: str | None,
    source_url: str | None,
) -> Video | None:
    video_ids: list[str] = []
    bvids: list[str] = []

    for value in (video_id, source_url):
        if not value:
            continue
        candidate = value.strip()
        if candidate:
            video_ids.append(candidate)

        bvid = _extract_bvid(candidate)
        if bvid:
            bvids.append(bvid)
            video_ids.append(f"b_{bvid}")

    seen_video_ids: set[str] = set()
    for candidate in video_ids:
        if candidate in seen_video_ids:
            continue
        seen_video_ids.add(candidate)
        video = db.query(Video).filter(Video.video_id == candidate).first()
        if video:
            return video
        if candidate.isdigit():
            video = db.query(Video).filter(Video.id == int(candidate)).first()
            if video:
                return video

    seen_bvids: set[str] = set()
    for bvid in bvids:
        if bvid in seen_bvids:
            continue
        seen_bvids.add(bvid)
        video = db.query(Video).filter(Video.bvid == bvid).first()
        if video:
            return video

    if source_url:
        return db.query(Video).filter(Video.url == source_url).first()

    return None


def _parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None

    start_raw, _, end_raw = range_header.removeprefix("bytes=").partition("-")
    try:
        if start_raw:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
        else:
            suffix_size = int(end_raw)
            start = max(0, file_size - suffix_size)
            end = file_size - 1
    except ValueError:
        return None

    if start < 0 or start >= file_size:
        return None
    return start, min(end, file_size - 1)


def _iter_file_range(path: Path, start: int, end: int):
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _stream_local_file(path: Path, request: Request) -> StreamingResponse:
    file_size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    range_header = request.headers.get("range")
    file_range = _parse_range_header(range_header, file_size)

    if file_range is None:
        headers = {
            "accept-ranges": "bytes",
            "content-length": str(file_size),
        }
        return StreamingResponse(
            _iter_file_range(path, 0, file_size - 1),
            headers=headers,
            media_type=media_type,
        )

    start, end = file_range
    headers = {
        "accept-ranges": "bytes",
        "content-length": str(end - start + 1),
        "content-range": f"bytes {start}-{end}/{file_size}",
    }
    return StreamingResponse(
        _iter_file_range(path, start, end),
        status_code=206,
        headers=headers,
        media_type=media_type,
    )


def _snapshot_path(video_path: Path, seconds: int) -> Path:
    snapshot_dir = video_path.parent / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir / f"{seconds:06d}.jpg"


def _generate_snapshot_sync(video_path: Path, output_path: Path, seconds: int) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-ss",
            str(max(0, seconds)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "ffmpeg 截图失败").strip()
        raise RuntimeError(detail[-500:])


def _bilibili_embed_url(source_url: str, info: dict | None = None) -> str | None:
    bvid = None
    if info:
        bvid = info.get("id") or info.get("display_id")
        if not (isinstance(bvid, str) and bvid.startswith("BV")):
            bvid = None

    if not bvid:
        match = re.search(r"BV[0-9A-Za-z]{10}", source_url)
        bvid = match.group(0) if match else None

    if not bvid:
        return None

    return (
        "https://player.bilibili.com/player.html"
        f"?bvid={quote(bvid)}&page=1&high_quality=1&autoplay=0"
    )


def _is_progressive_browser_format(fmt: dict) -> bool:
    url = fmt.get("url")
    ext = str(fmt.get("ext") or "").lower()
    protocol = str(fmt.get("protocol") or "").lower()
    vcodec = fmt.get("vcodec")
    acodec = fmt.get("acodec")

    if not url or vcodec in (None, "none") or acodec in (None, "none"):
        return False
    if ext not in {"mp4", "m4v", "webm", "mov"}:
        return False
    return protocol in {"http", "https"} or protocol.startswith("http")


def _choose_player_format(info: dict, quality: str) -> dict | None:
    target = _target_height(quality)
    formats = [fmt for fmt in info.get("formats") or [] if _is_progressive_browser_format(fmt)]
    if not formats and _is_progressive_browser_format(info):
        return info
    if not formats:
        return None

    under_target = [fmt for fmt in formats if int(fmt.get("height") or 0) <= target]
    pool = under_target or formats

    return max(
        pool,
        key=lambda fmt: (
            str(fmt.get("ext") or "").lower() == "mp4",
            int(fmt.get("height") or 0),
            float(fmt.get("tbr") or fmt.get("vbr") or 0),
        ),
    )


def _extract_player_info_sync(source_url: str, quality: str) -> dict:
    import yt_dlp

    from app.core.cookie_store import get_cookie
    from app.processor import build_cookie_opts, cleanup_temp_cookie, save_browser_cookies_to_cache

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    opts.update(build_cookie_opts())

    browser_cache_path = opts.pop("_browser_cache", None)
    temp_cookie = opts.pop("_temp_cookie", False)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source_url, download=False)
            if browser_cache_path and ydl.cookiejar:
                try:
                    save_browser_cookies_to_cache(browser_cache_path, ydl.cookiejar)
                except Exception:
                    pass
    finally:
        if temp_cookie:
            cleanup_temp_cookie({"cookiefile": opts.get("cookiefile"), "_temp_cookie": True})

    if not info:
        raise HTTPException(status_code=400, detail="无法解析视频播放信息")

    if info.get("_type") == "playlist" and info.get("entries"):
        entries = [entry for entry in info.get("entries") or [] if entry]
        if entries:
            info = entries[0]

    selected = _choose_player_format(info, quality)
    embed_url = _bilibili_embed_url(source_url, info)
    if not selected:
        return {
            "title": info.get("title") or "Bilibili 视频",
            "source_url": source_url,
            "webpage_url": info.get("webpage_url") or source_url,
            "direct_url": None,
            "embed_url": embed_url,
            "cover_url": info.get("thumbnail") or None,
            "duration_seconds": int(info["duration"]) if info.get("duration") else None,
            "format_id": None,
            "ext": None,
            "height": None,
            "http_headers": {},
            "player_type": "embed",
        }

    direct_url = selected.get("url")
    if not direct_url:
        raise HTTPException(status_code=400, detail="解析到的播放地址为空")

    http_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": info.get("webpage_url") or source_url,
        "Accept": "*/*",
    }
    for key, value in (info.get("http_headers") or {}).items():
        if isinstance(value, str) and key.lower() not in {"cookie", "host"}:
            http_headers[key] = value
    for key, value in (selected.get("http_headers") or {}).items():
        if isinstance(value, str) and key.lower() not in {"cookie", "host"}:
            http_headers[key] = value

    cookie = get_cookie("bilibili") or ""
    if cookie:
        http_headers["Cookie"] = cookie

    return {
        "title": info.get("title") or "Bilibili 视频",
        "source_url": source_url,
        "webpage_url": info.get("webpage_url") or source_url,
        "direct_url": direct_url,
        "embed_url": embed_url,
        "cover_url": info.get("thumbnail") or None,
        "duration_seconds": int(info["duration"]) if info.get("duration") else None,
        "format_id": str(selected.get("format_id") or ""),
        "ext": selected.get("ext"),
        "height": int(selected["height"]) if selected.get("height") else None,
        "http_headers": http_headers,
        "player_type": "native",
    }


async def _resolve_player_info(source_url: str, quality: str) -> dict:
    if not _is_supported_bilibili_url(source_url):
        raise HTTPException(status_code=400, detail="当前播放器仅支持 Bilibili 链接")

    cache_key = f"{quality}:{source_url}"
    cached = _PLAYER_CACHE.get(cache_key)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, _extract_player_info_sync, source_url, quality)
    _PLAYER_CACHE[cache_key] = (now + _PLAYER_CACHE_TTL_SECONDS, info)
    return info


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
    options = {
        "quality": body.quality,
        "transcriber": body.transcriber,
        "keep_video": body.keep_video,
        "provider_id": body.provider_id,
        "model_name": body.model_name,
        "format": body.format or [],
        "style": body.style,
        "extras": body.extras,
        "video_understanding": body.video_understanding,
        "video_interval": body.video_interval,
        "grid_size": body.grid_size or [],
        "platform": body.platform,
        "client_task_id": body.task_id,
    }
    task = await orchestrator.start_task(body.url, options=options)
    return {"task_id": task.task_id, "video_id": task.video_id, "status": task.status.value}


@router.post("/player/resolve", response_model=VideoPlayerResponse)
async def resolve_video_player(body: VideoPlayerRequest, db: Session = Depends(get_db)):
    """解析当前笔记视频的可播放地址。

    Cookie 只在后端使用，前端拿到的是本地代理流地址，避免泄露登录态。
    """
    local_stream_url = None
    local_video = _find_video_for_player(db, body.video_id, body.url)
    if _resolve_local_video_path(local_video) and local_video:
        local_stream_url = _video_local_stream_path(local_video.video_id)

    if local_stream_url and local_video:
        embed_url = _bilibili_embed_url(body.url)
        return VideoPlayerResponse(
            title=local_video.title or "本地视频",
            source_url=body.url,
            webpage_url=local_video.url or body.url,
            stream_url=local_stream_url,
            local_stream_url=local_stream_url,
            embed_url=embed_url,
            cover_url=local_video.cover_url,
            duration_seconds=int(local_video.duration_seconds) if local_video.duration_seconds else None,
            format_id="local-file",
            ext=Path(local_video.video_path or "").suffix.removeprefix(".") or "mp4",
            is_proxy_stream=True,
            player_type="local",
        )

    info = await _resolve_player_info(body.url, body.quality)
    stream_url = None
    if info.get("direct_url"):
        stream_url = (
            "/api/v1/videos/player/stream"
            f"?source={quote(body.url, safe='')}&quality={quote(body.quality, safe='')}"
        )
    return VideoPlayerResponse(
        title=info["title"],
        source_url=info["source_url"],
        webpage_url=info.get("webpage_url"),
        stream_url=stream_url,
        local_stream_url=None,
        embed_url=info.get("embed_url"),
        cover_url=info.get("cover_url"),
        duration_seconds=info.get("duration_seconds"),
        format_id=info.get("format_id"),
        ext=info.get("ext"),
        height=info.get("height"),
        is_proxy_stream=bool(stream_url),
        player_type=info.get("player_type") or ("native" if stream_url else "embed"),
    )


@router.get("/player/stream")
async def stream_video_player(
    request: Request,
    source: str = Query(..., min_length=1),
    quality: str = Query("1080p"),
):
    """代理 B 站视频流，转发 Range 请求以支持拖动进度条。"""
    info = await _resolve_player_info(source, quality)
    direct_url = info.get("direct_url")
    if not direct_url:
        raise HTTPException(
            status_code=409,
            detail="B 站当前只返回分离音视频流，请使用嵌入播放器播放",
        )

    headers = dict(info.get("http_headers") or {})
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=None, follow_redirects=True)
    upstream_request = client.build_request("GET", direct_url, headers=headers)
    upstream = await client.send(upstream_request, stream=True)

    response_headers = {}
    for header in (
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "cache-control",
        "etag",
        "last-modified",
    ):
        value = upstream.headers.get(header)
        if value:
            response_headers[header] = value

    response_headers.setdefault("accept-ranges", "bytes")

    async def iter_stream():
        try:
            async for chunk in upstream.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        iter_stream(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type", "video/mp4"),
    )


@router.get("/{video_id}/media")
async def stream_local_video_media(
    video_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """播放已下载到本地的视频文件，支持 Range 拖动。"""
    video = _find_video_for_player(db, video_id, None)
    path = _resolve_local_video_path(video)
    if not path:
        raise HTTPException(status_code=404, detail="本地视频文件不存在")
    return _stream_local_file(path, request)


@router.get("/{video_id}/snapshot")
async def get_video_snapshot(
    video_id: str,
    time_seconds: float = Query(0, alias="time", ge=0),
    db: Session = Depends(get_db),
):
    """按时间点提取一帧关键截图，生成后缓存在视频目录。"""
    video = _find_video_for_player(db, video_id, None)
    video_path = _resolve_local_video_path(video)
    if not video_path:
        raise HTTPException(status_code=404, detail="本地视频文件不存在，无法生成截图")

    seconds = max(0, int(time_seconds))
    output_path = _snapshot_path(video_path, seconds)
    if not output_path.exists():
        try:
            await asyncio.to_thread(_generate_snapshot_sync, video_path, output_path, seconds)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="ffmpeg 未安装或不在 PATH 中")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"生成截图失败: {exc}")

    return FileResponse(output_path, media_type="image/jpeg")


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
    # Cancel an in-flight pipeline task before removing local artifacts.
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator:
        for task_id, task in list(getattr(orchestrator, "_tasks", {}).items()):
            if task.video_id == video_id:
                orchestrator.cancel_task(task_id)
                break

    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    freed = 0
    locked_files: list[dict[str, str]] = []

    def unlink_artifact(path_value: str | None) -> None:
        nonlocal freed
        if not path_value:
            return
        p = Path(path_value)
        if not p.exists():
            return
        try:
            size = p.stat().st_size
            p.unlink(missing_ok=True)
            freed += size
        except PermissionError as exc:
            locked_files.append({"path": str(p), "reason": str(exc) or "文件正被其他程序占用"})
        except OSError as exc:
            locked_files.append({"path": str(p), "reason": str(exc) or type(exc).__name__})

    unlink_artifact(video.video_path)
    unlink_artifact(video.audio_path)

    note = db.query(Note).filter(Note.video_id == video.id).first()
    deleted_chunks = 0
    if note:
        unlink_artifact(note.file_path)
        deleted_chunks = note.total_chunks or 0
    await MockStore().delete_chunks(str(video.id))
    db.delete(video)
    db.commit()
    return {
        "code": 0,
        "message": "partial_success" if locked_files else "success",
        "data": {
            "deleted_video": True,
            "deleted_notes": bool(note),
            "deleted_chunks": deleted_chunks,
            "deleted_vectors": deleted_chunks,
            "freed_space_bytes": freed,
            "locked_files": locked_files,
        },
    }
