"""
Transcriber protocol: transcribe audio/video to text.
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol

from app.schemas.transcript import TranscriptResult


class Transcriber(Protocol):
    """Transcribe audio/video file to structured text."""

    async def transcribe(self, audio_path: Path) -> TranscriptResult:
        ...
