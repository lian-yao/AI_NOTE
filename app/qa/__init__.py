"""
问答引擎协议：基于笔记内容回答问题。
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import SearchResult


class QAEngine(Protocol):
    """基于检索上下文回答问题。"""

    async def answer(self, question: str, context: list[SearchResult]) -> str:
        """根据上下文生成回答。"""
