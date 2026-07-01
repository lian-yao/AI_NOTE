"""
Transcription result schemas.
"""
from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
    confidence: float | None = None


class TranscriptResult(BaseModel):
    segments: list[TranscriptSegment]
    full_text: str
    language: str | None = None
    duration_seconds: float | None = None
