"""
Retriever protocol: multi-strategy retrieval.
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import SearchResult


class Retriever(Protocol):
    """Combine keyword, vector, and hybrid search."""

    async def retrieve(self, query: str, note_id: str | None = None, top_k: int = 5) -> list[SearchResult]:
        ...
