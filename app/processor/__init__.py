"""
Processor protocol: transform transcript into structured content.
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import Chunk
from app.schemas.transcript import TranscriptResult


class Processor(Protocol):
    """Split / clean / enrich transcript into structured chunks."""

    async def process(self, transcript: TranscriptResult, note_id: str) -> list[Chunk]:
        ...
