"""
Video 数据模型。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Video(Base):
    """视频元数据。"""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="系统内部视频 ID（b_BVxxx 或 av_xxx）"
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, comment="用户输入的原始链接")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    uploader: Mapped[str | None] = mapped_column(String(256))
    uploader_uid: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    bvid: Mapped[str | None] = mapped_column(String(32))
    avid: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
        comment="pending / downloading / transcribing / generating / storing / completed / failed"
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    audio_path: Mapped[str | None] = mapped_column(Text)
    video_path: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tasks = relationship("Task", back_populates="video", cascade="all, delete-orphan")
    note = relationship("Note", back_populates="video", uselist=False, cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="video", cascade="all, delete-orphan")
