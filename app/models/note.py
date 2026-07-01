"""
Note 数据模型：视频笔记（一对一关系）。
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Note(Base):
    """笔记元数据，实际内容存储在文件系统中。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False, comment="笔记 Markdown 文件路径")
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text, comment="关键词，JSON 数组字符串")
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    video = relationship("Video", back_populates="note")
    chunks = relationship("Chunk", back_populates="note", cascade="all, delete-orphan")
