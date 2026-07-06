"""
Provider persistence helpers shared by provider and model APIs.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.provider import EnabledModel, LLMProvider


API_KEY_PLACEHOLDER = "******"


def _provider_type(value: str | None) -> str:
    if value == "custom":
        return "openai-compatible"
    return value or "openai-compatible"


def default_provider_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "tongyi",
            "name": "通义千问",
            "logo": "tongyi",
            "type": "tongyi",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": settings.tongyi_api_key,
            "enabled": True,
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "logo": "deepseek",
            "type": "openai-compatible",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": settings.deepseek_api_key,
            "enabled": True,
        },
    ]


def default_enabled_model_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if settings.tongyi_api_key:
        rows.append({"provider_id": "tongyi", "model_name": settings.tongyi_model})
    if settings.deepseek_api_key:
        rows.append({"provider_id": "deepseek", "model_name": settings.deepseek_model})
    return rows


def seed_default_providers(db: Session) -> bool:
    """Insert built-in providers when missing, preserving user edits."""
    changed = False
    for row in default_provider_rows():
        provider = db.get(LLMProvider, row["id"])
        if provider is None:
            db.add(LLMProvider(**row))
            changed = True
            continue

        # Let env-provided keys backfill an empty DB value, but never overwrite user edits.
        if not provider.api_key and row.get("api_key"):
            provider.api_key = row["api_key"]
            changed = True
    return changed


def seed_default_enabled_models(db: Session) -> bool:
    changed = seed_default_providers(db)
    for row in default_enabled_model_rows():
        existing = (
            db.query(EnabledModel)
            .filter(
                EnabledModel.provider_id == row["provider_id"],
                EnabledModel.model_name == row["model_name"],
            )
            .first()
        )
        if existing is None:
            db.add(EnabledModel(**row, enabled=True))
            changed = True
    return changed


def provider_to_dict(provider: LLMProvider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "logo": provider.logo,
        "type": provider.type,
        "base_url": provider.base_url,
        "enabled": provider.enabled,
        "has_api_key": bool(provider.api_key),
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def enabled_model_to_dict(model: EnabledModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "model_name": model.model_name,
        "enabled": model.enabled,
        "created_at": model.created_at,
    }


def should_update_api_key(value: str | None) -> bool:
    return value is not None and value != API_KEY_PLACEHOLDER


def normalize_provider_type(value: str | None) -> str:
    return _provider_type(value)
