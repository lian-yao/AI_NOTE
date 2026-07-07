"""WebSocket 端点：任务实时进度推送。"""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.pipeline.orchestrator import PipelineEvent

router = APIRouter(prefix="/ws", tags=["ws"])


class ConnectionManager:
    """管理 WebSocket 连接，按 task_id 分组。
    
    连接建立时注册，断开时清理。
    收到 EventBus 事件后转发给对应 task_id 的所有连接。
    """

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, ws: WebSocket):
        """注册新连接。"""
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(task_id, set()).add(ws)

    async def disconnect(self, task_id: str, ws: WebSocket):
        """移除已断开的连接。"""
        async with self._lock:
            if task_id in self._connections:
                self._connections[task_id].discard(ws)
                if not self._connections[task_id]:
                    del self._connections[task_id]

    async def broadcast(self, task_id: str, event: PipelineEvent):
        """向指定 task 的所有 WS 连接推送事件。"""
        async with self._lock:
            connections = self._connections.get(task_id, set()).copy()
        for ws in connections:
            try:
                await ws.send_json({
                    "event": event.event,
                    "data": {
                        "task_id": event.task_id,
                        "video_id": event.video_id,
                        "stage": event.stage,
                        "status": event.status,
                        "progress": event.progress,
                        "message": event.message,
                    },
                })
            except Exception as e:
                logger.debug(f"WebSocket 发送失败 ({task_id}): {e}")


manager = ConnectionManager()


@router.websocket("/task/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    """每个任务一条 WS 连接，接收进度推送。"""
    await manager.connect(task_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(task_id, websocket)
