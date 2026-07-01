"""
重试逻辑：指数退避重试 + 降级方案。

按流水线文档 5.1 节定义各阶段重试策略。
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Awaitable
from typing import TypeVar

T = TypeVar("T")

# 阶段默认重试配置
STAGE_RETRY_CONFIG: dict[str, dict] = {
    "parse":    {"max_retries": 0, "base_delay": 0,   "backoff": 1},
    "download": {"max_retries": 3, "base_delay": 5,   "backoff": 5},
    "extract":  {"max_retries": 2, "base_delay": 5,   "backoff": 1},
    "transcribe": {"max_retries": 2, "base_delay": 10, "backoff": 2},
    "generate": {"max_retries": 3, "base_delay": 10,  "backoff": 1},
    "store":    {"max_retries": 3, "base_delay": 5,   "backoff": 1},
}


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 5.0,
    backoff: float = 2.0,
    jitter: bool = True,
) -> T:
    """指数退避重试。

    Args:
        fn: 异步可调用对象
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 基础等待秒数
        backoff: 退避乘数（每次重试 delay *= backoff）
        jitter: 是否添加随机抖动（±25%）

    Returns:
        fn 的返回值

    Raises:
        最后一次重试的异常
    """
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            wait = delay
            if jitter:
                wait *= 0.75 + random.random() * 0.5  # ±25%
            await asyncio.sleep(wait)
            delay *= backoff

    # 理论上不会到这里，但让类型检查器满意
    assert last_exc is not None
    raise last_exc
