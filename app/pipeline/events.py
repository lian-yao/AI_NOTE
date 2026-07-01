"""
事件总线：处理流水线生命周期事件的进程内事件分发机制。
连接 PipelineOrchestrator → WebSocket 消费者。
"""
from __future__ import annotations

from typing import Any, Callable

from app.pipeline.orchestrator import PipelineEvent

# 事件处理器类型：接收 PipelineEvent 并返回 None
EventHandler = Callable[[PipelineEvent], None]


class EventBus:
    """
    进程内事件总线。
    编排器在此发射事件；WebSocket 管理器订阅后转发给连接中的客户端。
    """

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}  # 按事件类型分组的处理器
        self._all_handlers: list[EventHandler] = []          # 全局处理器（接收所有事件）

    def on(self, event_type: str, handler: EventHandler):
        """注册指定事件类型的处理器。"""
        self._handlers.setdefault(event_type, []).append(handler)

    def on_any(self, handler: EventHandler):
        """注册全局处理器（接收所有事件类型）。"""
        self._all_handlers.append(handler)

    def emit(self, event: PipelineEvent):
        """将事件分发至所有匹配的处理器。"""
        for handler in self._all_handlers:
            try:
                handler(event)
            except Exception:
                pass
        for handler in self._handlers.get(event.event, []):
            try:
                handler(event)
            except Exception:
                pass
