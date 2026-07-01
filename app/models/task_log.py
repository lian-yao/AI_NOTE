"""
TaskLog 数据模型：任务的详细日志。
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskLog(Base):
    """任务日志：记录处理过程中的详细信息。"""

    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="INFO",
        comment="DEBUG / INFO / WARN / ERROR"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, comment="JSON 格式的详细信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    task = relationship("Task", back_populates="logs")
