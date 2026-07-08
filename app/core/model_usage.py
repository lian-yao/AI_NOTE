"""Model usage preferences for QA and embeddings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.llm.client import LLMClient, get_provider_llm_client
from app.models.provider import EnabledModel, LLMProvider
from app.store.embedder import EmbeddingClient, EmbeddingConfigurationError

MODEL_USAGE_CONFIG_FILE = Path(settings.data_dir) / "model_usage_config.json"

DEFAULT_MODEL_USAGE_CONFIG = {
    "qa_provider_id": "",
    "qa_model_name": "",
    "embedding_provider_id": "",
    "embedding_model_name": "",
}

PLACEHOLDER_MODEL_IDS = {"backend", "mock-backend", "mock-provider", "preview"}


def load_model_usage_config() -> dict[str, str]:
    if not MODEL_USAGE_CONFIG_FILE.exists():
        return dict(DEFAULT_MODEL_USAGE_CONFIG)
    try:
        raw = json.loads(MODEL_USAGE_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_MODEL_USAGE_CONFIG)
    return normalize_model_usage_config(raw)


def save_model_usage_config(data: dict[str, Any]) -> dict[str, str]:
    config = normalize_model_usage_config(data)
    MODEL_USAGE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_USAGE_CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config


def clear_model_usage_for_provider(provider_id: str) -> dict[str, str]:
    config = load_model_usage_config()
    changed = False
    provider = (provider_id or "").strip()
    for purpose in ("qa", "embedding"):
        provider_key = f"{purpose}_provider_id"
        model_key = f"{purpose}_model_name"
        if config.get(provider_key) == provider:
            config[provider_key] = ""
            config[model_key] = ""
            changed = True
    return save_model_usage_config(config) if changed else config


def clear_model_usage_for_model(provider_id: str, model_name: str) -> dict[str, str]:
    config = load_model_usage_config()
    changed = False
    provider = (provider_id or "").strip()
    model = (model_name or "").strip()
    for purpose in ("qa", "embedding"):
        provider_key = f"{purpose}_provider_id"
        model_key = f"{purpose}_model_name"
        if config.get(provider_key) == provider and config.get(model_key) == model:
            config[provider_key] = ""
            config[model_key] = ""
            changed = True
    return save_model_usage_config(config) if changed else config


def prune_model_usage_config(db: Session) -> dict[str, str]:
    """Drop stale provider/model selections and keep .env fallback available."""
    config = load_model_usage_config()
    changed = False
    for purpose in ("qa", "embedding"):
        provider_key = f"{purpose}_provider_id"
        model_key = f"{purpose}_model_name"
        provider_id = config.get(provider_key, "")
        model_name = config.get(model_key, "")
        if not provider_id and not model_name:
            continue
        if not has_model_pair(provider_id, model_name):
            config[provider_key] = ""
            config[model_key] = ""
            changed = True
            continue
        try:
            validate_model_pair(db, provider_id, model_name)
        except ValueError as exc:
            logger.warning(f"默认用途模型已失效，自动回退: {purpose}={provider_id}/{model_name}, {exc}")
            config[provider_key] = ""
            config[model_key] = ""
            changed = True
    return save_model_usage_config(config) if changed else config


def normalize_model_usage_config(data: dict[str, Any] | None) -> dict[str, str]:
    source = data or {}
    config = dict(DEFAULT_MODEL_USAGE_CONFIG)
    for key in config:
        value = source.get(key, "")
        config[key] = value.strip() if isinstance(value, str) else ""
    return config


def has_model_pair(provider_id: str | None, model_name: str | None) -> bool:
    provider = (provider_id or "").strip()
    model = (model_name or "").strip()
    if provider in PLACEHOLDER_MODEL_IDS or model in PLACEHOLDER_MODEL_IDS:
        return False
    return bool(provider and model)


def validate_model_pair(db: Session, provider_id: str, model_name: str) -> None:
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise ValueError("Provider 不存在")
    if not provider.enabled:
        raise ValueError("Provider 已禁用")

    model = (
        db.query(EnabledModel)
        .filter(
            EnabledModel.provider_id == provider_id,
            EnabledModel.model_name == model_name,
            EnabledModel.enabled.is_(True),
        )
        .first()
    )
    if not model:
        raise ValueError("模型未启用")


def get_provider_client(db: Session, provider_id: str, model_name: str) -> LLMClient:
    validate_model_pair(db, provider_id, model_name)
    provider = db.get(LLMProvider, provider_id)
    return get_provider_llm_client(provider, model_name)


def get_configured_llm_client(
    db: Session,
    *,
    purpose: str = "qa",
    provider_id: str | None = None,
    model_name: str | None = None,
) -> LLMClient | None:
    """Resolve chat LLM: explicit request > usage config > caller fallback."""
    if has_model_pair(provider_id, model_name):
        return get_provider_client(db, provider_id.strip(), model_name.strip())

    config = load_model_usage_config()
    configured_provider = config.get(f"{purpose}_provider_id", "")
    configured_model = config.get(f"{purpose}_model_name", "")
    if has_model_pair(configured_provider, configured_model):
        try:
            return get_provider_client(db, configured_provider, configured_model)
        except ValueError as exc:
            logger.warning(f"默认问答模型不可用，将使用兜底模型: {exc}")
            clear_model_usage_for_model(configured_provider, configured_model)

    return None


def get_embedding_client(db: Session | None = None) -> EmbeddingClient:
    """Resolve embedding client: Provider usage config > .env compatibility."""
    config = load_model_usage_config()
    provider_id = config.get("embedding_provider_id", "")
    model_name = config.get("embedding_model_name", "")

    if not has_model_pair(provider_id, model_name):
        return EmbeddingClient()

    owns_session = False
    if db is None:
        from app.core.database import SessionLocal

        db = SessionLocal()
        owns_session = True

    try:
        try:
            validate_model_pair(db, provider_id, model_name)
        except ValueError as exc:
            logger.warning(f"默认 Embedding 模型不可用，将使用 .env 兜底: {exc}")
            clear_model_usage_for_model(provider_id, model_name)
            return EmbeddingClient()
        provider = db.get(LLMProvider, provider_id)
        api_key = (provider.api_key or "").strip() if provider else ""
        base_url = (provider.base_url or "").strip() if provider else ""
        if not api_key:
            raise EmbeddingConfigurationError("Embedding Provider API Key 未配置")
        if not base_url:
            raise EmbeddingConfigurationError("Embedding Provider Base URL 未配置")
        return EmbeddingClient(api_key=api_key, model=model_name, base_url=base_url)
    finally:
        if owns_session:
            db.close()
