"""
Provider 管理（模拟实现，后续由角色A完善）
默认载入通义千问和 DeepSeek，API Key 从 settings 读取。
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/providers", tags=["providers"])

# ---------- 内存存储 ----------
_providers: dict[str, dict] = {}

def _init_default_providers():
    """初始化默认 Provider（通义 & DeepSeek）"""
    default_providers = [
        {
            "id": "tongyi",
            "name": "通义千问",
            "logo": "tongyi",
            "type": "tongyi",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "api_key": settings.tongyi_api_key,   # 真实 key，但 get 时不会返回明文
            "enabled": True,
            "created_at": "2026-07-03T00:00:00",
            "updated_at": "2026-07-03T00:00:00"
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "logo": "deepseek",
            "type": "openai-compatible",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": settings.deepseek_api_key,
            "enabled": True,
            "created_at": "2026-07-03T00:00:00",
            "updated_at": "2026-07-03T00:00:00"
        }
    ]
    for p in default_providers:
        _providers[p["id"]] = p

# 初始化
_init_default_providers()

# ---------- 请求/响应模型 ----------
class CreateProviderRequest(BaseModel):
    name: str
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str
    api_key: str
    enabled: bool = True

class UpdateProviderRequest(BaseModel):
    name: str
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str
    api_key: str | None = None   # 允许不更新 API Key
    enabled: bool = True

# ---------- 接口 ----------
@router.get("")
async def list_providers():
    """获取 Provider 列表（不返回明文 api_key）"""
    items = []
    for p in _providers.values():
        items.append({
            "id": p["id"],
            "name": p["name"],
            "logo": p["logo"],
            "type": p["type"],
            "base_url": p["base_url"],
            "enabled": p["enabled"],
            "has_api_key": bool(p.get("api_key")),
            "created_at": p["created_at"],
            "updated_at": p["updated_at"]
        })
    return ApiResponse(data={"items": items})

@router.post("")
async def create_provider(req: CreateProviderRequest):
    """新增 Provider"""
    new_id = str(uuid.uuid4())
    _providers[new_id] = {
        "id": new_id,
        "name": req.name,
        "logo": req.logo,
        "type": req.type,
        "base_url": req.base_url,
        "api_key": req.api_key,
        "enabled": req.enabled,
        "created_at": "2026-07-03T12:00:00",
        "updated_at": "2026-07-03T12:00:00"
    }
    return ApiResponse(data={"id": new_id})

@router.get("/{provider_id}")
async def get_provider(provider_id: str):
    p = _providers.get(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    return ApiResponse(data={
        "id": p["id"],
        "name": p["name"],
        "logo": p["logo"],
        "type": p["type"],
        "base_url": p["base_url"],
        "enabled": p["enabled"],
        "has_api_key": bool(p.get("api_key")),
        "created_at": p["created_at"],
        "updated_at": p["updated_at"]
    })

@router.put("/{provider_id}")
async def update_provider(provider_id: str, req: UpdateProviderRequest):
    p = _providers.get(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    # 更新字段
    p["name"] = req.name
    p["logo"] = req.logo
    p["type"] = req.type
    p["base_url"] = req.base_url
    if req.api_key is not None:
        p["api_key"] = req.api_key
    p["enabled"] = req.enabled
    p["updated_at"] = "2026-07-03T12:00:00"
    return ApiResponse(data={"updated": True})

@router.delete("/{provider_id}")
async def delete_provider(provider_id: str):
    if provider_id not in _providers:
        raise HTTPException(404, "Provider not found")
    # 不允许删除默认的两个？实际可以删除，但这里允许
    del _providers[provider_id]
    # 同时删除该 Provider 下所有已启用的模型（如果有 models 存储，需要一并清理，此处略）
    return ApiResponse(data={"deleted": True, "deleted_models": 0})

@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, body: dict = None):
    """测试连接（模拟）"""
    p = _providers.get(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    # 简单模拟，实际可调用 /models 接口
    return ApiResponse(data={"ok": True, "latency_ms": 150})

@router.get("/{provider_id}/remote-models")
async def remote_models(provider_id: str):
    """获取远程模型列表（模拟）"""
    p = _providers.get(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    # 根据 provider 类型返回不同 mock 数据
    if p["id"] == "tongyi":
        models = [
            {"id": "qwen-plus", "object": "model", "display_name": "Qwen-Plus", "owned_by": "tongyi"},
            {"id": "qwen-turbo", "object": "model", "display_name": "Qwen-Turbo", "owned_by": "tongyi"},
        ]
    elif p["id"] == "deepseek":
        models = [
            {"id": "deepseek-chat", "object": "model", "display_name": "DeepSeek Chat", "owned_by": "deepseek"},
        ]
    else:
        models = [{"id": "gpt-4o-mini", "object": "model", "display_name": "GPT-4o mini", "owned_by": "openai"}]
    return ApiResponse(data={"models": models})