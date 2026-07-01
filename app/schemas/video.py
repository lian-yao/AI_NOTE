"""
Video Pydantic 数据模型。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class VideoBase(BaseModel):
    url: str
    title: str
    uploader: Optional[str] = None
    uploader_uid: Optional[str] = None
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    cover_url: Optional[str] = None
    bvid: Optional[str] = None
    avid: Optional[int] = None


class VideoCreate(VideoBase):
    video_id: str
    status: str = "pending"
    file_size: Optional[int] = None
    audio_path: Optional[str] = None
    video_path: Optional[str] = None


class VideoResponse(VideoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: str
    status: str
    file_size: Optional[int] = None
    audio_path: Optional[str] = None
    video_path: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
