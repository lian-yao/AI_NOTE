"""Network proxy configuration API."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/network", tags=["network"])

_runtime_config = {
    "enabled": False,
    "url": "",
    "effective": "",
}


@router.get("/proxy")
def get_proxy_config():
    return _runtime_config


class ProxyUpdate(BaseModel):
    enabled: bool
    url: str = ""


@router.put("/proxy")
def update_proxy_config(body: ProxyUpdate):
    _runtime_config["enabled"] = body.enabled
    _runtime_config["url"] = body.url or ""
    _runtime_config["effective"] = body.url if body.enabled else ""
    return dict(_runtime_config)
