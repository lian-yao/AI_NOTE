"""
Pydantic 数据模型。
"""
from app.schemas.video import VideoCreate, VideoResponse
from app.schemas.note import NoteCreate, NoteResponse
from app.schemas.chunk import ChunkBase, SearchResult
from app.schemas.task import TaskCreate, TaskResponse, TaskLogResponse
from app.schemas.transcript import TranscriptSegment, TranscriptResult
from app.schemas.qa import QARequest, QAResponse

__all__ = [
    "VideoCreate", "VideoResponse",
    "NoteCreate", "NoteResponse",
    "ChunkBase", "SearchResult",
    "TaskCreate", "TaskResponse", "TaskLogResponse",
    "TranscriptSegment", "TranscriptResult",
    "QARequest", "QAResponse",
]
