"""
Store protocol: vector storage and similarity search.
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import Chunk, SearchResult


class Store(Protocol):
    """Vector store for document chunks."""

    async def add_chunks(self, chunks: list[Chunk]) -> None:
        ...

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[SearchResult]:
        ...

    async def delete_chunks(self, note_id: str) -> None:
        ...
