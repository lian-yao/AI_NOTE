"""
FastAPI 应用入口
"""
import sys
import time
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        return  # 没有事件循环，忽略推送
    asyncio.create_task(ws_manager.broadcast(event.task_id, event))


@asynccontextmanager
async def lifespan(app: FastAPI):
    #  启动逻辑
    os.makedirs("data", exist_ok=True)
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


@app.get("/image_proxy")
async def image_proxy(url: str):
    """代理外部图片（B 站封面等），绕过 Referer/CORS 限制。"""
    import urllib.request
    from fastapi.responses import Response

    if not url.startswith(("http://", "https://")):
        return Response(status_code=400, content="Invalid URL")

    def _fetch() -> tuple[bytes, str]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError("Image too large")
            return body, resp.headers.get_content_type() or "image/jpeg"

    try:
        content, media_type = await asyncio.to_thread(_fetch)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception:
        return Response(status_code=502, content="Proxy failed")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    # loop="asyncio" 让 uvicorn 使用 Python 默认事件循环策略，
    # 而非 Windows 上硬编码 SelectorEventLoop（不支持子进程管道）
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="asyncio")