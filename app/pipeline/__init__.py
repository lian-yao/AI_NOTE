"""
管道协议：编排完整的视频处理工作流。
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.note import NoteResponse
from app.schemas.qa import QARequest, QAResponse


class Pipeline(Protocol):
    """视频处理与问答的全流程编排。"""

    async def process_video(self, source_url: str) -> NoteResponse:
        """处理视频：下载 -> 转写 -> 生成笔记。"""

    async def answer_question(self, request: QARequest) -> QAResponse:
        """基于笔记内容回答用户问题。"""
