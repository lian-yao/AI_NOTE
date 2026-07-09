"""
FastAPI 应用入口
"""
import base64
import sys
import time
import os
import asyncio
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx

# Windows 必须使用 ProactorEventLoop 才能支持 asyncio.subprocess 的管道
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.core.config import settings
from app.core.logger import setup_logger, log_requests
from app.core.database import engine, Base
from app import models
from app.api import api_router
from app.api.v1 import router as v1_router
from app.pipeline import PipelineOrchestrator, EventBus
from app.api.v1.ws import manager as ws_manager
from app.pipeline.orchestrator import PipelineEvent
from app.core.errors import register_error_handlers

# 初始化日志（import 阶段执行，早于 lifespan）

logger = setup_logger(settings.data_dir)


def _forward_to_ws(event: PipelineEvent):
    """将流水线事件通过 WebSocket 推送给前端。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass  # 没有事件循环时静默忽略
    else:
        loop.create_task(ws_manager.broadcast(event.task_id, event))


@asynccontextmanager
async def lifespan(app: FastAPI):
    #  启动逻辑
    os.makedirs(settings.data_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    event_bus = EventBus()
    app.state.orchestrator = PipelineOrchestrator()
    app.state.event_bus = event_bus
    app.state.orchestrator.on_progress(event_bus.emit)
    event_bus.on_any(_forward_to_ws)
    app.state.start_time = time.time()
    logger.info("Application started")

    yield  # 服务运行中

    # 关闭逻辑
    await logger.complete()
    logger.info("Application shutting down")



app = FastAPI(
    title="VideoNote - 视频知识沉淀与智能问答系统",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan  # 绑定生命周期
)

register_error_handlers(app)
api_router.include_router(v1_router)
app.include_router(api_router)
app.middleware("http")(log_requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #允许的源
    allow_credentials=True,#允许带cookie
    allow_methods=["*"],#允许的请求方法
    allow_headers=["*"],#允许的请求头
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/sys_check")
async def sys_check():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/image_proxy")
async def image_proxy(url: str = Query(..., min_length=1)):
    """Proxy external cover images so browser CORS/referrer checks do not break covers."""
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        media_type = header[5:].split(";")[0] or "application/octet-stream"
        content = (
            base64.b64decode(payload)
            if ";base64" in header
            else urllib.parse.unquote_to_bytes(payload)
        )
        return Response(content=content, media_type=media_type)

    if url.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                        ),
                        "Referer": "https://www.bilibili.com/",
                        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    },
                )
                resp.raise_for_status()
                content = resp.content
                if len(content) <= 8 * 1024 * 1024:
                    media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
                    if media_type.startswith("image/"):
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
  <text x="120" y="285" font-family="Arial, sans-serif" font-size="40" fill="#f9fafb">Cover unavailable</text>
</svg>
""".strip()
    return Response(content=placeholder, media_type="image/svg+xml")


if __name__ == "__main__":
    import uvicorn
    # loop="asyncio" 让 uvicorn 使用 Python 默认事件循环策略，
    # 而非 Windows 上硬编码 SelectorEventLoop（不支持子进程管道）
    backend_port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=backend_port, loop="asyncio")
