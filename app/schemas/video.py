"""
Video Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class VideoBase(BaseModel):
    source_url: str
    title: Optional[str] = None


class VideoCreate(VideoBase):
    pass


class VideoResponse(VideoBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    duration_seconds: Optional[float] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
