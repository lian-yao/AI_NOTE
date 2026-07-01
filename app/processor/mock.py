"""
Mock 文本处理实现。
"""
from app.schemas.chunk import Chunk
from app.schemas.transcript import TranscriptResult


class MockProcessor:
    """将转录结果按片段拆分为文本块。"""

    async def process(self, transcript: TranscriptResult, note_id: str) -> list[Chunk]:
        return [
            Chunk(note_id=note_id, content=seg.text, chunk_index=i)
            for i, seg in enumerate(transcript.segments)
        ]
