"""
LLM Provider and enabled model persistence.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LLMProvider(Base):
    """LLM provider configuration."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    logo: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="openai-compatible")
    base_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    api_key: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    models = relationship("EnabledModel", back_populates="provider", cascade="all, delete-orphan")


class EnabledModel(Base):
    """A model enabled for generation and chat."""

    __tablename__ = "enabled_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_enabled_models_provider_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    provider = relationship("LLMProvider", back_populates="models")
