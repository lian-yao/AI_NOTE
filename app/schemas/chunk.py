"""
Chunk 数据模型：文本切片，用于向量检索。
"""
from typing import Optional

from pydantic import BaseModel


class ChunkBase(BaseModel):
    """文本切片。"""
    chunk_id: str
    video_id: int
    note_id: int
    chunk_index: int
    section_title: Optional[str] = None
    content: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    chroma_id: Optional[str] = None
    token_count: int = 0
    embedding_dim: int = 1536


class SearchResult(BaseModel):
    """检索结果：切片 + 相关性分数。"""
    chunk: ChunkBase
    score: float
