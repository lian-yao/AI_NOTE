"""
Note Pydantic 数据模型（一对一，内容存储在文件系统）。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    video_id: int
    file_path: str
    summary: Optional[str] = None
    keywords: Optional[str] = None
    total_chunks: int = 0
    section_count: int = 0
    char_count: int = 0
    model_used: Optional[str] = None


class NoteCreate(NoteBase):
    pass


class NoteResponse(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
