"""
FastAPI 应用入口
"""
from fastapi import FastAPI
from app.core.config import settings
from app.core.logger import setup_logger

# 初始化日志，并拿到logger实例
logger = setup_logger(settings.data_dir)

app = FastAPI(
    title="VideoNote - 视频知识沉淀与智能问答系统",
    version="0.1.0",
    docs_url="/docs",
)


@app.on_event("startup")
async def startup():
    logger.info("Application started")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Application shutting down")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}