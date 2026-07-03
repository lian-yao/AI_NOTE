"""LLM Provider management API."""
from __future__ import annotations
import json, os, time, httpx
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/providers", tags=["providers"])
DATA_FILE = "data/providers.json"

DEFAULT_PROVIDERS = [
    {"id": "tongyi", "name": "Tongyi", "logo": "tongyi", "type": "tongyi",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "api_key": "", "enabled": True},
    {"id": "deepseek", "name": "DeepSeek", "logo": "deepseek", "type": "openai-compatible",
     "base_url": "https://api.deepseek.com/v1",
     "api_key": "", "enabled": True},
]


def _load():
    if not os.path.isfile(DATA_FILE):
        return list(DEFAULT_PROVIDERS)
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_PROVIDERS)


def _save(providers):
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(providers, f, ensure_ascii=False, indent=2)


class ProviderCreate(BaseModel):
    name: str
    logo: str = "custom"
    type: str = "openai-compatible"
    base_url: str = ""
    api_key: str = ""
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = None
    logo: str | None = None
    type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


class TestConnectionPayload(BaseModel):
    model_name: str = ""


@router.get("")
def list_providers():
    items = _load()
    result = []
    for p in items:
        result.append({
            "id": p["id"],
            "name": p["name"],
            "logo": p.get("logo", "custom"),
            "type": p.get("type", "openai-compatible"),
            "base_url": p.get("base_url", ""),
            "has_api_key": bool(p.get("api_key")),
            "api_key": p.get("api_key", ""),
            "enabled": p.get("enabled", True),
        })
    return {"items": result, "total": len(result)}


@router.post("")
def create_provider(body: ProviderCreate):
    providers = _load()
    pid = body.name.lower().replace(" ", "_")
    if any(p["id"] == pid for p in providers):
        raise HTTPException(400, f"Provider '{pid}' already exists")
    provider = {
        "id": pid,
        "name": body.name,
        "logo": body.logo,
        "type": body.type,
        "base_url": body.base_url,
        "api_key": body.api_key,
        "enabled": body.enabled,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    providers.append(provider)
    _save(providers)
    return {"id": pid, "message": "Provider created"}


@router.get("/{provider_id}")
def get_provider(provider_id: str):
    providers = _load()
    for p in providers:
        if p["id"] == provider_id:
            return {
                "id": p["id"], "name": p["name"],
                "logo": p.get("logo", "custom"), "type": p.get("type", "openai-compatible"),
                "base_url": p.get("base_url", ""), "has_api_key": bool(p.get("api_key")),
                "api_key": p.get("api_key", ""), "enabled": p.get("enabled", True),
            }
    raise HTTPException(404, "Provider not found")


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: ProviderUpdate):
    providers = _load()
    for p in providers:
        if p["id"] == provider_id:
            for key in ("name", "logo", "type", "base_url", "api_key", "enabled"):
                val = getattr(body, key, None)
                if val is not None:
                    p[key] = val
            p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save(providers)
            return {"message": "Provider updated"}
    raise HTTPException(404, "Provider not found")


@router.delete("/{provider_id}")
def delete_provider(provider_id: str):
    providers = _load()
    for i, p in enumerate(providers):
        if p["id"] == provider_id:
            providers.pop(i)
            _save(providers)
            return {"message": "Provider deleted"}
    raise HTTPException(404, "Provider not found")


@router.post("/{provider_id}/test")
async def test_connection(provider_id: str, body: TestConnectionPayload):
    providers = _load()
    for p in providers:
        if p["id"] == provider_id:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(f"{p.get('base_url','')}/chat/completions",
                        headers={"Authorization": f"Bearer {p.get('api_key','')}"},
                        json={"model": body.model_name or "gpt-3.5-turbo", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                    )
                    if resp.status_code == 200:
                        return {"status": "ok", "message": "Connection successful"}
                    return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            except Exception as e:
                return {"status": "error", "message": str(e)[:200]}
    raise HTTPException(404, "Provider not found")


@router.get("/{provider_id}/remote-models")
async def fetch_remote_models(provider_id: str):
    """Fetch models available from the provider API."""
    from app.core.config import settings
    models = []
    if provider_id == "tongyi":
        models = ["qwen-plus", "qwen-turbo", "qwen-max", "qwen2.5-72b-instruct"]
    elif provider_id == "deepseek":
        models = ["deepseek-chat", "deepseek-reasoner"]
    return {"models": models, "data": models}
