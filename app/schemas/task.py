"""
Task / TaskLog Pydantic 数据模型。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TaskBase(BaseModel):
    video_id: int
    type: str
    status: str = "pending"
    progress: int = 0
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


class TaskCreate(TaskBase):
    task_id: str


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TaskLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    level: str
    message: str
    detail: Optional[str] = None
    created_at: datetime
