"""
QA protocol: question answering over note context.
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import SearchResult


class QAEngine(Protocol):
    """Answer questions based on retrieved context."""

    async def answer(self, question: str, context: list[SearchResult]) -> str:
        ...
