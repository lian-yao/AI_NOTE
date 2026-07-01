"""
Mock 文本处理实现。
"""
from app.schemas.chunk import ChunkBase
from app.schemas.transcript import TranscriptResult


class MockProcessor:
    """将转录结果按片段拆分为文本块。"""

    async def process(
        self, transcript: TranscriptResult, note_id: int, video_id: str
    ) -> list[ChunkBase]:
        return [
            ChunkBase(
                chunk_id=f"{video_id}_{i}",
                video_id=0,  # 会在 service 中通过 db flush 后得到真正的 id
                note_id=note_id,
                content=seg.text,
                chunk_index=i,
                section_title=f"章节 {i + 1}",
                start_time=seg.start,
                end_time=seg.end,
            )
            for i, seg in enumerate(transcript.segments)
        ]
