"""EnabledModel 数据模型：用户启用的模型。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnabledModel(Base):
    """用户启用的模型记录。"""

    __tablename__ = "enabled_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="关联的 Provider ID（如 tongyi / deepseek）"
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
