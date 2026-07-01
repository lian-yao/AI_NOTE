"""
检索器协议：多策略检索。
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import SearchResult


class Retriever(Protocol):
    """结合关键字、向量、混合检索。"""

    async def retrieve(self, query: str, note_id: str | None = None, top_k: int = 5) -> list[SearchResult]:
        """检索与查询相关的文本块。"""
