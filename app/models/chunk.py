"""
Chunk 数据模型：笔记文本切片，用于向量检索。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Chunk(Base):
    """笔记文本切片，对应 ChromaDB 中的一个向量。"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="格式：{video_id}_{chunkIndex}"
    )
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float | None] = mapped_column(Float)
    end_time: Mapped[float | None] = mapped_column(Float)
    chroma_id: Mapped[str | None] = mapped_column(String(128), comment="ChromaDB 中的记录 ID")
    token_count: Mapped[int | None] = mapped_column(Integer, default=0)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, default=1536)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    video = relationship("Video", back_populates="chunks")
    note = relationship("Note", back_populates="chunks")
