"""
日志配置与请求日志中间件。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import Request
from loguru import logger


def setup_logger(data_dir: str = "./data", level: str = "DEBUG"):
    """初始化日志配置。

    参数:
        data_dir: 日志文件存放目录
        level:    文件日志级别（终端始终为 INFO）
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # 终端输出：INFO 级别，带颜色
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )

    # 文件输出：可配置级别，自动轮转
    logger.add(
        log_dir / "videonote_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level=level,
        enqueue=True,
    )

    return logger


async def log_requests(request: Request, call_next):
    """请求日志中间件：记录方法、路径、状态码、耗时。"""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "{method} {path} {status} {duration:.0f}ms",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration=duration_ms,
    )
    return response
