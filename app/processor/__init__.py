"""
处理器协议：将转录文本转换为结构化内容。
"""
from __future__ import annotations
from typing import Protocol

from app.schemas.chunk import Chunk
from app.schemas.transcript import TranscriptResult


class Processor(Protocol):
    """对转录结果进行拆分、清洗、丰富，生成结构化文本块。"""

    async def process(self, transcript: TranscriptResult, note_id: str) -> list[Chunk]:
        ...
