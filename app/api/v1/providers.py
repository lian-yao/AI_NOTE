"""
Provider 管理（模拟实现，后续由角色A完善）
默认载入通义千问和 DeepSeek，API Key 从 settings 读取。
"""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
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
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
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
    name: str | None = None       # 允许只更新部分字段
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str | None = None
    api_key: str | None = None   # 允许不更新 API Key
    enabled: bool | None = None

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
    # 更新字段（仅当请求中提供了值，支持部分更新）
    if req.name is not None:
        p["name"] = req.name
    if req.logo:
        p["logo"] = req.logo
    if req.type:
        p["type"] = req.type
    if req.base_url is not None:
        p["base_url"] = req.base_url
    if req.api_key is not None:
        p["api_key"] = req.api_key
    if req.enabled is not None:
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
    """测试连接（真实调用提供者 API）"""
    p = _providers.get(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    api_key = p.get("api_key", "")
    base_url = p.get("base_url", "").rstrip("/")
    if not api_key:
        return ApiResponse(code=1, message="API Key 未配置", data={"ok": False})
    if not base_url:
        return ApiResponse(code=1, message="Base URL 未配置", data={"ok": False})
    import time
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            t0 = time.time()
            if p["type"] == "tongyi":
                # 通义千问 chat 接口
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "qwen-plus", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
            else:
                # OpenAI 兼容格式
                resp = await client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            latency = int((time.time() - t0) * 1000)
            return ApiResponse(data={"ok": True, "latency_ms": latency})
    except httpx.TimeoutException:
        return ApiResponse(code=1, message="连接超时", data={"ok": False})
    except httpx.HTTPStatusError as e:
        return ApiResponse(code=1, message=f"API 返回错误码 {e.response.status_code}，请检查 API Key", data={"ok": False})
    except Exception as e:
        return ApiResponse(code=1, message=f"连接失败: {str(e)[:100]}", data={"ok": False})

@router.get("/{provider_id}/remote-models")
async def remote_models(provider_id: str):
    """
    获取远程模型列表（通过 Provider 的真实 API 获取）
    支持 OpenAI 兼容格式：GET {base_url}/models
    """
    p = _providers.get(provider_id)
    if not p:
        return ApiResponse(code=1, message="Provider 不存在", data={"models": []})

    api_key = p.get("api_key", "")
    base_url = p.get("base_url", "").rstrip("/")

    if not api_key:
        return ApiResponse(code=1, message="API Key 未配置，请先设置 API Key", data={"models": []})

    models_url = f"{base_url}/models"

    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析 OpenAI 兼容格式：{ data: [{ id, object, owned_by }, ...] }
        # 也兼容直接返回数组的情况
        raw_list = data if isinstance(data, list) else data.get("data", [])

        models = []
        for m in raw_list:
            if not isinstance(m, dict):
                continue
            model_id = m.get("id", "")
            if not model_id:
                continue
            models.append({
                "id": model_id,
                "object": m.get("object", "model"),
                "display_name": m.get("display_name", "") or m.get("id", ""),
                "owned_by": m.get("owned_by", p["id"]),
            })

        return ApiResponse(data={"models": models})

    except httpx.TimeoutException:
        return ApiResponse(code=1, message=f"请求 Provider 模型列表超时，请检查网络连接（{models_url}）", data={"models": []})
    except httpx.HTTPStatusError as e:
        return ApiResponse(code=1, message=f"Provider 返回错误（{e.response.status_code}），请检查 API Key 和 Base URL 是否正确", data={"models": []})
    except Exception as e:
        return ApiResponse(code=1, message=f"获取远程模型列表失败：{str(e)[:200]}", data={"models": []})