"""
Note Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    video_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    raw_transcript: Optional[str] = None


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    raw_transcript: Optional[str] = None


class NoteResponse(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
