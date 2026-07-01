"""
FastAPI 应用入口
"""
import time
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import setup_logger, log_requests
from app.core.database import engine, Base
from app import models
from app.api import api_router
from app.api.v1 import router as v1_router
from app.pipeline import PipelineOrchestrator, EventBus
from app.core.errors import register_error_handlers

# 初始化日志（import 阶段执行，早于 lifespan）

logger = setup_logger(settings.data_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    #  启动逻辑
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    event_bus = EventBus()
    app.state.orchestrator = PipelineOrchestrator()
    app.state.event_bus = event_bus
    app.state.orchestrator.on_progress(event_bus.emit)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)