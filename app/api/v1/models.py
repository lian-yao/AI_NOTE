"""Enabled models management API."""
from __future__ import annotations
import json, os, time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/models", tags=["models"])
DATA_FILE = "data/enabled_models.json"

DEFAULT_MODELS = [
    {"id": 1, "provider_id": "tongyi", "model_name": "qwen-plus", "enabled": True, "created_at": "2026-07-01T00:00:00"},
    {"id": 2, "provider_id": "tongyi", "model_name": "qwen-turbo", "enabled": False, "created_at": "2026-07-01T00:00:00"},
    {"id": 3, "provider_id": "deepseek", "model_name": "deepseek-chat", "enabled": True, "created_at": "2026-07-01T00:00:00"},
    {"id": 4, "provider_id": "deepseek", "model_name": "deepseek-reasoner", "enabled": False, "created_at": "2026-07-01T00:00:00"},
]


def _load():
    if not os.path.isfile(DATA_FILE):
        return list(DEFAULT_MODELS)
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_MODELS)


def _save(data):
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class AddModelPayload(BaseModel):
    provider_id: str
    model_name: str


@router.get("")
def list_models(provider_id: str | None = Query(None), enabled: bool | None = Query(None)):
    items = _load()
    if provider_id:
        items = [m for m in items if m["provider_id"] == provider_id]
    if enabled is not None:
        items = [m for m in items if m.get("enabled", False) == enabled]
    return {"items": items, "total": len(items)}


@router.post("")
def add_model(body: AddModelPayload):
    items = _load()
    mid = max((m["id"] for m in items), default=0) + 1
    items.append({
        "id": mid,
        "provider_id": body.provider_id,
        "model_name": body.model_name,
        "enabled": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save(items)
    return {"id": mid, "message": "Model added"}


@router.delete("/{model_id}")
def delete_model(model_id: int):
    items = _load()
    for i, m in enumerate(items):
        if m["id"] == model_id:
            items.pop(i)
            _save(items)
            return {"message": "Model deleted"}
    raise HTTPException(404, "Model not found")
