"""Provider 数据模型：LLM 提供商配置。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Provider(Base):
    """LLM 提供商配置（用户自定义的 Provider）。"""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="唯一标识（用于 API 调用时的 provider_id）"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    logo: Mapped[str] = mapped_column(String(64), default="", comment="图标标识")
    type: Mapped[str] = mapped_column(String(64), default="openai-compatible", comment="tongyi / openai-compatible")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    api_key_encrypted: Mapped[str] = mapped_column(String(512), default="", comment="加密存储的 API Key")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
