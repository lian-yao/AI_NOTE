"""
文本块与检索结果数据模型。
"""
from pydantic import BaseModel


class Chunk(BaseModel):
    """文本块：用于向量存储与检索。"""
    note_id: str
    content: str
    chunk_index: int = 0
    embedding: list[float] | None = None
    metadata: dict | None = None


class SearchResult(BaseModel):
    """检索结果：文本块 + 相关性分数。"""
    chunk: Chunk
    score: float
