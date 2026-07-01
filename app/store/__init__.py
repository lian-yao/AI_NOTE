"""
存储协议：向量存储与相似度检索。
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import ChunkBase, SearchResult


class Store(Protocol):
    """向量数据库接口。"""

    async def add_chunks(self, chunks: list[ChunkBase]) -> None:
        """批量添加文本块。"""

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[SearchResult]:
        """向量相似度检索。"""

    async def delete_chunks(self, note_id: str) -> None:
        """删除指定笔记的所有文本块。"""
