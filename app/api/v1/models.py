"""
已启用模型管理（模拟）
默认启用通义和 DeepSeek 模型（从 settings 读取模型名）
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/models", tags=["models"])

# 内存存储
_models: List[dict] = []
_id_counter = 1

# 初始化默认启用模型（从 settings 读取默认模型）
_default_models = []
if settings.tongyi_api_key:
    _default_models.append({
        "id": 1,
        "provider_id": "tongyi",
        "model_name": settings.tongyi_model,
        "enabled": True,
        "created_at": "2026-07-03T00:00:00"
    })
if settings.deepseek_api_key:
    _default_models.append({
        "id": 2,
        "provider_id": "deepseek",
        "model_name": settings.deepseek_model,
        "enabled": True,
        "created_at": "2026-07-03T00:00:00"
    })
_models = _default_models
_id_counter = len(_models) + 1

class CreateModelRequest(BaseModel):
    provider_id: str
    model_name: str

@router.get("")
async def list_models(provider_id: Optional[str] = None, enabled: bool = True):
    """获取已启用模型列表"""
    items = []
    for m in _models:
        if provider_id and m["provider_id"] != provider_id:
            continue
        if m["enabled"] != enabled:
            continue
        items.append(m)
    return ApiResponse(data={"items": items})

@router.post("")
async def enable_model(req: CreateModelRequest):
    """启用一个模型"""
    # 检查是否已存在
    for m in _models:
        if m["provider_id"] == req.provider_id and m["model_name"] == req.model_name:
            m["enabled"] = True
            return ApiResponse(data=m)
    # 新增
    new_model = {
        "id": _id_counter,
        "provider_id": req.provider_id,
        "model_name": req.model_name,
        "enabled": True,
        "created_at": "2026-07-03T12:00:00"
    }
    _models.append(new_model)
    _id_counter += 1
    return ApiResponse(data=new_model)

@router.delete("/{model_id:int}")
async def delete_model(model_id: int):
    """禁用或删除模型（这里直接删除）"""
    for idx, m in enumerate(_models):
        if m["id"] == model_id:
            del _models[idx]
            return ApiResponse(data={"deleted": True})
    raise HTTPException(404, "Model not found")