"""
问答请求/响应数据模型。
"""
from pydantic import BaseModel, Field
from app.schemas.chunk import SearchResult


class QARequest(BaseModel):
    """问答请求。"""
    question: str
    video_id: str | None = None
    note_id: str | None = None
    top_k: int = 5
    provider_id: str | None = None
    model_name: str | None = None
    history: list[dict] = Field(default_factory=list)


class QAResponse(BaseModel):
    """问答响应。"""
    answer: str
    sources: list[SearchResult]
