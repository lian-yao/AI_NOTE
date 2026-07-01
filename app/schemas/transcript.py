"""
转录结果数据模型。
"""
from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    """转录片段：时间范围内的文本块。"""
    text: str
    start: float
    end: float
    confidence: float | None = None


class TranscriptResult(BaseModel):
    """完整转录结果。"""
    segments: list[TranscriptSegment]
    full_text: str
    language: str | None = None
    duration_seconds: float | None = None
