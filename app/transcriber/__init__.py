"""
转写器协议：将音频/视频转录为结构化文本。
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol

from app.schemas.transcript import TranscriptResult


class Transcriber(Protocol):
    """音频/视频文件转写接口。"""

    async def transcribe(self, audio_path: Path) -> TranscriptResult:
        ...
