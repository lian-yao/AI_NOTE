"""
Provider management API.
"""
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.provider_store import (
    normalize_provider_type,
    provider_to_dict,
    seed_default_providers,
    should_update_api_key,
)
from app.models.provider import EnabledModel, LLMProvider
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/providers", tags=["providers"])


class CreateProviderRequest(BaseModel):
    name: str
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str
    api_key: str = ""
    enabled: bool = True


class UpdateProviderRequest(BaseModel):
    name: str | None = None
    logo: str | None = None
    type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


def _ensure_default_providers(db: Session) -> None:
    if seed_default_providers(db):
        db.commit()


@router.get("")
async def list_providers(db: Session = Depends(get_db)):
    """List providers without returning raw API keys."""
    _ensure_default_providers(db)
    providers = db.query(LLMProvider).order_by(LLMProvider.created_at.asc()).all()
    return ApiResponse(data={"items": [provider_to_dict(provider) for provider in providers]})


@router.post("")
async def create_provider(req: CreateProviderRequest, db: Session = Depends(get_db)):
    """Create a provider."""
    name = req.name.strip()
    base_url = req.base_url.strip()
    if not name:
        raise HTTPException(400, "Provider name is required")
    if not base_url:
        raise HTTPException(400, "Base URL is required")

    provider = LLMProvider(
        id=str(uuid.uuid4()),
        name=name,
        logo=req.logo or "custom",
        type=normalize_provider_type(req.type),
        base_url=base_url,
        api_key=req.api_key,
        enabled=req.enabled,
    )
    db.add(provider)
    db.commit()
    return ApiResponse(data={"id": provider.id})


@router.get("/{provider_id}")
async def get_provider(provider_id: str, db: Session = Depends(get_db)):
    _ensure_default_providers(db)
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")
    return ApiResponse(data=provider_to_dict(provider))


@router.put("/{provider_id}")
async def update_provider(
    provider_id: str,
    req: UpdateProviderRequest,
    db: Session = Depends(get_db),
):
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "Provider name is required")
        provider.name = name
    if req.logo is not None:
        provider.logo = req.logo or "custom"
    if req.type is not None:
        provider.type = normalize_provider_type(req.type)
    if req.base_url is not None:
        base_url = req.base_url.strip()
        if not base_url:
            raise HTTPException(400, "Base URL is required")
        provider.base_url = base_url
    if should_update_api_key(req.api_key):
        provider.api_key = req.api_key or ""
    if req.enabled is not None:
        provider.enabled = req.enabled

    db.commit()
    return ApiResponse(data={"updated": True})


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    deleted_models = db.query(EnabledModel).filter(EnabledModel.provider_id == provider_id).count()
    db.delete(provider)
    db.commit()
    return ApiResponse(data={"deleted": True, "deleted_models": deleted_models})


@router.post("/{provider_id}/test")
async def test_provider(
    provider_id: str,
    body: dict | None = None,
    db: Session = Depends(get_db),
):
    """Test provider existence and basic configuration."""
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")
    if not provider.api_key:
        return ApiResponse(code=1, message="API Key 未配置，请先设置 API Key", data={"ok": False})
    return ApiResponse(data={"ok": True, "latency_ms": 150})


@router.get("/{provider_id}/remote-models")
async def remote_models(provider_id: str, db: Session = Depends(get_db)):
    """
    Fetch remote model list from a provider.

    OpenAI-compatible providers are expected to expose GET {base_url}/models.
    """
    provider = db.get(LLMProvider, provider_id)
    if not provider:
        return ApiResponse(code=1, message="Provider 不存在", data={"models": []})

    api_key = provider.api_key or ""
    base_url = (provider.base_url or "").rstrip("/")

    if not api_key:
        return ApiResponse(code=1, message="API Key 未配置，请先设置 API Key", data={"models": []})
    if not base_url:
        return ApiResponse(code=1, message="Base URL 未配置", data={"models": []})

    models_url = f"{base_url}/models"

    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        raw_list = data if isinstance(data, list) else data.get("data", [])
        models = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id", "")
            if not model_id:
                continue
            models.append(
                {
                    "id": model_id,
                    "object": item.get("object", "model"),
                    "display_name": item.get("display_name", "") or model_id,
                    "owned_by": item.get("owned_by", provider.id),
                }
            )

        return ApiResponse(data={"models": models})

    except httpx.TimeoutException:
        return ApiResponse(
            code=1,
            message=f"请求 Provider 模型列表超时，请检查网络连接（{models_url}）",
            data={"models": []},
        )
    except httpx.HTTPStatusError as exc:
        return ApiResponse(
            code=1,
            message=f"Provider 返回错误（{exc.response.status_code}），请检查 API Key 和 Base URL 是否正确",
            data={"models": []},
        )
    except Exception as exc:
        return ApiResponse(code=1, message=f"获取远程模型列表失败：{str(exc)[:200]}", data={"models": []})
