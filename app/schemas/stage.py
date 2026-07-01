"""
流水线阶段结果与事件数据模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageResult:
    """单个处理阶段的返回结果。"""
    success: bool
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineEvent:
    """流水线进度事件（用于 EventBus / WebSocket 推送）。"""
    event: str       # progress / completed / error
    task_id: str
    video_id: str
    stage: str
    status: str      # running / completed / failed
    progress: int    # 0-100
    message: str
