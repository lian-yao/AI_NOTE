from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from .store import store, utc_now


def ok(data: Any | None = None, message: str = "success") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": {} if data is None else data,
    }


def page_items(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_size = min(100, max(1, int(page_size or 20)))
    start = (safe_page - 1) * safe_size
    return {
        "items": items[start : start + safe_size],
        "total": len(items),
        "page": safe_page,
        "page_size": safe_size,
    }


app = FastAPI(
    title="AI Note Mock Backend",
    version="0.1.0-mock",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


@app.get("/health")
async def root_health() -> dict[str, Any]:
    return {"status": "ok", "version": "0.1.0-mock", "service": "mock-backend"}


@app.get("/image_proxy")
async def image_proxy(url: str) -> Response:
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        media_type = header[5:].split(";")[0] or "application/octet-stream"
        if ";base64" in header:
            content = base64.b64decode(payload)
        else:
            content = urllib.parse.unquote_to_bytes(payload)
        return Response(content=content, media_type=media_type)

    if url.startswith(("http://", "https://")):
        def fetch_remote_image() -> tuple[bytes, str]:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    ),
                    "Referer": "https://www.bilibili.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                content = response.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError("remote image is too large")
                return content, response.headers.get_content_type() or "image/jpeg"

        try:
            content, media_type = await asyncio.to_thread(fetch_remote_image)
            return Response(
                content=content,
                media_type=media_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )
        except Exception:
            pass

    placeholder = """
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <rect width="960" height="540" fill="#111827"/>
  <rect x="80" y="80" width="800" height="380" rx="28" fill="#1f2937"/>
  <text x="120" y="250" font-family="Arial, sans-serif" font-size="44" fill="#f9fafb">
    Mock image proxy
  </text>
  <text x="120" y="320" font-family="Arial, sans-serif" font-size="24" fill="#9ca3af">
    External cover image placeholder
  </text>
</svg>
""".strip()
    return Response(content=placeholder, media_type="image/svg+xml")


@app.get("/mock-cover/{video_id}.svg")
@app.get("/static/mock-cover/{video_id}.svg")
async def mock_cover(video_id: str) -> Response:
    safe_title = video_id[:32]
    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#172554"/>
      <stop offset="0.48" stop-color="#0f766e"/>
      <stop offset="1" stop-color="#f59e0b"/>
    </linearGradient>
  </defs>
  <rect width="960" height="540" fill="url(#g)"/>
  <circle cx="790" cy="100" r="140" fill="#ffffff" opacity="0.11"/>
  <circle cx="120" cy="430" r="170" fill="#000000" opacity="0.18"/>
  <rect x="70" y="72" width="820" height="396" rx="30" fill="#020617" opacity="0.62"/>
  <text x="104" y="178" font-family="Arial, sans-serif" font-size="34" fill="#f8fafc">
    Mock Backend Service
  </text>
  <text x="104" y="270" font-family="Arial, sans-serif" font-size="52" font-weight="700" fill="#ffffff">
    {safe_title}
  </text>
  <text x="104" y="346" font-family="Arial, sans-serif" font-size="26" fill="#cbd5e1">
    Video summary, transcript, QA and settings data
  </text>
</svg>
""".strip()
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/system/ready")
async def system_ready() -> dict[str, Any]:
    return ok({"ready": True, "version": "0.1.0-mock", "service": "mock-backend"})


@router.get("/system/health")
async def system_health() -> dict[str, Any]:
    return ok(
        {
            "status": "healthy",
            "database": "mock",
            "vector_store": "mock",
            "llm_api": "mock",
            "embedding_api": "mock",
            "disk_space": "ok",
            "uptime_seconds": store.uptime_seconds(),
        }
    )


@router.get("/system/config")
async def get_system_config() -> dict[str, Any]:
    return ok(store.clone(store.system_config))


@router.put("/system/config")
async def update_system_config(body: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "llm_provider",
        "llm_model",
        "transcriber_mode",
        "whisper_model_size",
        "whisper_device",
        "embedding_model",
        "retrieval_top_k",
        "data_dir",
        "video_retention",
    }
    updated: list[str] = []
    for key, value in body.items():
        if key in allowed:
            store.system_config[key] = value
            updated.append(key)
    return ok({"updated_fields": updated})


@router.post("/system/config/save")
async def save_system_config() -> dict[str, Any]:
    return ok({}, "mock config saved in memory")


@router.get("/system/stats")
async def system_stats() -> dict[str, Any]:
    videos = list(store.videos.values())
    notes = list(store.notes.values())
    return ok(
        {
            "total_videos": len(videos),
            "completed_videos": sum(1 for item in videos if item.get("status") == "completed"),
            "total_notes": len(notes),
            "total_chunks": sum(int(item.get("total_chunks", 0)) for item in notes),
            "total_duration_hours": round(
                sum(int(item.get("duration_seconds") or 0) for item in videos) / 3600,
                2,
            ),
            "storage_usage_bytes": sum(int(item.get("file_size") or 0) for item in videos),
            "disk_free_bytes": 64 * 1024 * 1024 * 1024,
        }
    )


@router.get("/system/deploy-status")
async def deploy_status() -> dict[str, Any]:
    return ok(
        {
            "backend": {
                "status": "ok",
                "port": 8010,
            },
            "cuda": {
                "available": False,
                "torch_installed": False,
                "version": None,
                "gpu_name": None,
            },
            "whisper": {
                "model_size": store.transcriber_config["whisper_model_size"],
                "transcriber_type": store.transcriber_config["transcriber_type"],
                "downloaded": True,
            },
            "ffmpeg": {
                "available": True,
            },
        }
    )


@router.post("/videos/parse")
async def parse_video(body: dict[str, Any]) -> dict[str, Any]:
    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    parsed = store.parse_video_url(url)
    parsed.pop("url", None)
    return ok(parsed)


@router.post("/videos/process")
async def process_video(body: dict[str, Any]) -> dict[str, Any]:
    return ok(store.create_task(body))


@router.get("/videos")
@router.get("/videos/")
async def list_videos(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    items = [store.get_task(task_id) for task_id in list(store.tasks)]
    del items
    videos = list(store.videos.values())
    if status:
        videos = [item for item in videos if item.get("status") == status]
    if search:
        needle = search.lower()
        videos = [item for item in videos if needle in str(item.get("title", "")).lower()]
    videos.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return ok(page_items(store.clone(videos), page, page_size))


@router.get("/videos/{video_id}")
async def get_video(video_id: str) -> dict[str, Any]:
    for task_id in list(store.tasks):
        store.get_task(task_id)
    video = store.videos.get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    data = store.clone(video)
    note = store.notes.get(video_id)
    if note:
        data["note"] = {
            "id": note["id"],
            "summary": note["summary"][:240],
            "keywords": note["keywords"],
            "total_chunks": note["total_chunks"],
            "section_count": note["section_count"],
            "char_count": note["char_count"],
            "created_at": note["created_at"],
        }
    data["tasks"] = [
        {
            "task_id": task["task_id"],
            "type": task["type"],
            "status": task["status"],
            "progress": task["progress"],
        }
        for task in store.tasks.values()
        if task.get("video_id") == video_id
    ]
    return ok(data)


@router.delete("/videos/{video_id}")
async def delete_video(video_id: str) -> dict[str, Any]:
    return ok(store.delete_video(video_id))


@router.get("/notes")
@router.get("/notes/")
async def list_notes() -> dict[str, Any]:
    notes = [
        {
            "id": note["id"],
            "video_id": note["video_id"],
            "file_path": note["file_path"],
            "summary": note["summary"][:240],
            "keywords": ",".join(note["keywords"]),
            "total_chunks": note["total_chunks"],
            "section_count": note["section_count"],
            "char_count": note["char_count"],
            "model_used": note["model_used"],
            "created_at": note["created_at"],
            "updated_at": note["updated_at"],
        }
        for note in store.notes.values()
    ]
    return ok(notes)


@router.post("/notes")
@router.post("/notes/")
async def create_note(body: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    video_id = str(body.get("video_id") or f"manual-{uuid.uuid4().hex[:8]}")
    note = {
        "id": store.next_note_id,
        "video_id": video_id,
        "video_title": f"Manual note {video_id}",
        "file_path": body.get("file_path") or f"./mock_backend/.data/notes/{video_id}.md",
        "summary": body.get("summary") or "# Manual mock note\n\nCreated through /notes.",
        "keywords": body.get("keywords") or ["manual", "mock"],
        "sections": [],
        "total_chunks": int(body.get("total_chunks") or 1),
        "section_count": int(body.get("section_count") or 1),
        "char_count": int(body.get("char_count") or 0),
        "model_used": body.get("model_used") or "mock-llm",
        "created_at": now,
        "updated_at": now,
        "raw_markdown": body.get("summary") or "# Manual mock note\n\nCreated through /notes.",
    }
    store.next_note_id += 1
    store.notes[video_id] = note
    return ok(note)


@router.get("/notes/{video_id}/raw")
async def get_note_raw(video_id: str) -> PlainTextResponse:
    note = store.notes.get(video_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    return PlainTextResponse(note["raw_markdown"], media_type="text/markdown; charset=utf-8")


@router.get("/notes/{video_id}")
async def get_note(video_id: str) -> dict[str, Any]:
    note = store.notes.get(video_id)
    if not note:
        note = next((item for item in store.notes.values() if str(item["id"]) == video_id), None)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    return ok(store.clone(note))


@router.post("/qa/ask", response_model=None)
async def ask(body: dict[str, Any]) -> dict[str, Any] | StreamingResponse:
    query = str(body.get("query") or body.get("question") or "").strip() or "What is this about?"
    video_id = body.get("video_id") or body.get("note_id")
    answer = store.qa_answer(query, str(video_id) if video_id else None)
    if body.get("stream"):
        async def events():
            for token in answer["answer"].split(" "):
                yield f"event: token\ndata: {json.dumps({'token': token + ' ', 'finish_reason': None})}\n\n"
                await asyncio.sleep(0.03)
            payload = {
                "references": answer["references"],
                "token_usage": answer["token_usage"],
            }
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")
    return ok(answer)


@router.post("/qa/ask-global")
async def ask_global(body: dict[str, Any]) -> dict[str, Any]:
    query = str(body.get("query") or body.get("question") or "").strip() or "Search globally"
    return ok(store.qa_answer(query))


@router.post("/qa/index")
async def index_qa(body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("task_id") and not body.get("video_id"):
        raise HTTPException(status_code=400, detail="task_id or video_id is required")
    return ok({"indexed": True, "status": "indexed"})


@router.get("/qa/index/status")
async def index_status(task_id: str | None = None, video_id: str | None = None) -> dict[str, Any]:
    if not task_id and not video_id:
        raise HTTPException(status_code=400, detail="task_id or video_id is required")
    return ok({"indexed": True, "status": "indexed"})


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task["status"] != "completed":
        task["result"] = None
    return ok(task)


@router.get("/tasks/{task_id}/logs")
async def task_logs(
    task_id: str,
    level: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    if task_id not in store.tasks:
        raise HTTPException(status_code=404, detail="task not found")
    logs = store.list_task_logs(task_id)
    if level:
        logs = [item for item in logs if item["level"].upper() == level.upper()]
    return ok(page_items(logs, page, page_size))


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str) -> dict[str, Any]:
    data = store.retry_task(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="task not found")
    return ok(data)


@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    return ok({"items": store.clone(store.providers)})


@router.post("/providers")
async def add_provider(body: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    provider_id = str(body.get("id") or f"provider-{uuid.uuid4().hex[:8]}")
    provider = {
        "id": provider_id,
        "name": body.get("name") or "Custom Mock Provider",
        "logo": body.get("logo") or "custom",
        "type": body.get("type") or "openai-compatible",
        "base_url": body.get("base_url") or "",
        "enabled": bool(body.get("enabled", True)),
        "has_api_key": bool(body.get("api_key")),
        "api_key": "******" if body.get("api_key") else "",
        "created_at": now,
        "updated_at": now,
    }
    store.providers.append(provider)
    store.remote_models.setdefault(provider_id, [])
    return ok({"id": provider_id})


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str) -> dict[str, Any]:
    provider = next((item for item in store.providers if item["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="provider not found")
    return ok(store.clone(provider))


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, body: dict[str, Any]) -> dict[str, Any]:
    provider = next((item for item in store.providers if item["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="provider not found")
    for key in ["name", "logo", "type", "base_url", "enabled"]:
        if key in body and body[key] is not None:
            provider[key] = body[key]
    if body.get("api_key"):
        provider["api_key"] = "******"
        provider["has_api_key"] = True
    provider["updated_at"] = utc_now()
    return ok({"updated": True})


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, Any]:
    before_models = len(store.models)
    store.providers = [item for item in store.providers if item["id"] != provider_id]
    store.models = [item for item in store.models if item["provider_id"] != provider_id]
    return ok({"deleted": True, "deleted_models": before_models - len(store.models)})


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, body: dict[str, Any]) -> dict[str, Any]:
    if not any(item["id"] == provider_id for item in store.providers):
        raise HTTPException(status_code=404, detail="provider not found")
    model_name = body.get("model_name") or "mock-llm"
    latency = 120 + len(str(model_name)) * 7
    return ok({"ok": True, "latency_ms": latency})


@router.get("/providers/{provider_id}/remote-models")
async def remote_models(provider_id: str) -> dict[str, Any]:
    return ok({"models": store.clone(store.remote_models.get(provider_id, []))})


@router.get("/models")
async def list_models(provider_id: str | None = None, enabled: bool | None = None) -> dict[str, Any]:
    models = store.clone(store.models)
    if provider_id:
        models = [item for item in models if item["provider_id"] == provider_id]
    if enabled is not None:
        models = [item for item in models if bool(item.get("enabled", True)) == enabled]
    return ok({"items": models})


@router.post("/models")
async def add_model(body: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(body.get("provider_id") or "")
    model_name = str(body.get("model_name") or "")
    if not provider_id or not model_name:
        raise HTTPException(status_code=400, detail="provider_id and model_name are required")
    existing = next(
        (
            item
            for item in store.models
            if item["provider_id"] == provider_id and item["model_name"] == model_name
        ),
        None,
    )
    if existing:
        return ok(existing)
    store.next_model_id += 1
    item = {
        "id": store.next_model_id,
        "provider_id": provider_id,
        "model_name": model_name,
        "enabled": True,
        "created_at": utc_now(),
    }
    store.models.append(item)
    return ok(item)


@router.delete("/models/{model_id}")
async def delete_model(model_id: int) -> dict[str, Any]:
    before = len(store.models)
    store.models = [item for item in store.models if int(item["id"]) != model_id]
    return ok({"deleted": len(store.models) != before})


@router.get("/transcribers/config")
async def get_transcriber_config() -> dict[str, Any]:
    return ok(store.clone(store.transcriber_config))


@router.put("/transcribers/config")
async def update_transcriber_config(body: dict[str, Any]) -> dict[str, Any]:
    updated: list[str] = []
    for key in ["transcriber_type", "whisper_model_size"]:
        if key in body and body[key]:
            store.transcriber_config[key] = body[key]
            updated.append(key)
    store.system_config["transcriber_mode"] = store.transcriber_config["transcriber_type"]
    store.system_config["whisper_model_size"] = store.transcriber_config["whisper_model_size"]
    return ok({"updated_fields": updated})


@router.get("/transcribers/models/status")
async def transcriber_models_status() -> dict[str, Any]:
    selected = store.transcriber_config["whisper_model_size"]
    sizes = store.transcriber_config["whisper_model_sizes"]
    return ok(
        {
            "whisper": [
                {
                    "model_size": size,
                    "downloaded": size == selected,
                    "downloading": False,
                    "failed": False,
                    "error": None,
                }
                for size in sizes
            ],
            "mlx_whisper": [
                {
                    "model_size": size,
                    "downloaded": False,
                    "downloading": False,
                    "failed": False,
                    "error": None,
                }
                for size in sizes
            ],
            "mlx_available": False,
        }
    )


@router.post("/transcribers/models/download")
async def download_transcriber_model(body: dict[str, Any]) -> dict[str, Any]:
    model_size = body.get("model_size") or store.transcriber_config["whisper_model_size"]
    transcriber_type = body.get("transcriber_type") or store.transcriber_config["transcriber_type"]
    store.transcriber_config["whisper_model_size"] = model_size
    return ok(
        {
            "model_size": model_size,
            "transcriber_type": transcriber_type,
            "downloading": False,
            "downloaded": True,
        }
    )


@router.get("/transcribers/whisper-models")
async def list_whisper_models() -> dict[str, Any]:
    return ok(
        {
            "builtin": store.clone(store.transcriber_config["whisper_builtin_models"]),
            "custom": store.clone(store.transcriber_config["whisper_custom_models"]),
        }
    )


@router.post("/transcribers/whisper-models")
async def add_whisper_model(body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    target = str(body.get("target") or "").strip()
    if not name or not target:
        raise HTTPException(status_code=400, detail="name and target are required")
    store.transcriber_config["whisper_custom_models"][name] = target
    return ok({"name": name, "target": target})


@router.delete("/transcribers/whisper-models/{name}")
async def delete_whisper_model(name: str) -> dict[str, Any]:
    deleted = store.transcriber_config["whisper_custom_models"].pop(name, None) is not None
    return ok({"deleted": deleted})


@router.get("/platforms/{platform}/cookie")
async def get_platform_cookie(platform: str) -> dict[str, Any]:
    cookie = store.cookies.get(platform, "")
    return ok({"platform": platform, "cookie": cookie})


@router.put("/platforms/{platform}/cookie")
async def update_platform_cookie(platform: str, body: dict[str, Any]) -> dict[str, Any]:
    store.cookies[platform] = str(body.get("cookie") or "")
    return ok({"platform": platform, "updated": True})


@router.get("/network/proxy")
async def get_proxy() -> dict[str, Any]:
    return ok(store.clone(store.proxy_config))


@router.put("/network/proxy")
async def update_proxy(body: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(body.get("enabled"))
    url = str(body.get("url") or "")
    store.proxy_config = {
        "enabled": enabled,
        "url": url,
        "effective": url if enabled else "",
    }
    return ok(store.clone(store.proxy_config))


@router.post("/uploads/videos")
async def upload_video(request: Request) -> dict[str, Any]:
    body = await request.body()
    head = body[:4096].decode("utf-8", errors="ignore")
    match = re.search(r'filename="([^"]+)"', head)
    filename = match.group(1) if match else "mock-upload.mp4"
    file_id = f"upload-{uuid.uuid4().hex[:12]}"
    data = {
        "file_id": file_id,
        "filename": filename,
        "size_bytes": len(body),
        "url": f"local://{file_id}",
    }
    store.uploads[file_id] = data
    return ok(data)


@router.websocket("/ws/task/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        last_status = None
        while True:
            task = store.get_task(task_id)
            if not task:
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {
                            "task_id": task_id,
                            "status": "failed",
                            "error_message": "task not found",
                            "retryable": False,
                        },
                    }
                )
                await asyncio.sleep(1)
                continue
            stage = store.task_stage(task)
            event_name = "completed" if stage["status"] == "completed" else "progress"
            if stage["status"] != last_status or event_name == "completed":
                await websocket.send_json(
                    {
                        "event": event_name,
                        "data": {
                            "task_id": task_id,
                            "video_id": task["video_id"],
                            "type": "generate",
                            "stage": stage["stage"],
                            "status": stage["status"],
                            "progress": stage["progress"],
                            "message": stage["message"],
                        },
                    }
                )
                last_status = stage["status"]
            if stage["status"] == "completed":
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return


app.include_router(router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail,
            "detail": exc.detail,
            "data": None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mock_backend.app:app", host="127.0.0.1", port=8010, reload=True)
