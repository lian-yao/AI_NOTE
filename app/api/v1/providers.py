"""
Provider 管理（数据库持久化）
默认内置通义千问和 DeepSeek（从 settings 读取），自定义 Provider 存入数据库。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx, uuid

from app.core.database import get_db
from app.core.config import settings
from app.models.provider import Provider
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/providers", tags=["providers"])

# ── 内置 Provider（从 settings 读取，不存 DB）──
_BUILTIN_PROVIDERS = []

def _init_builtin():
    global _BUILTIN_PROVIDERS
    items = []
    if settings.tongyi_api_key:
        items.append({
            "id": "tongyi", "name": "\u901a\u4e49\u5343\u95ee",
            "logo": "tongyi", "type": "tongyi",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "has_api_key": True,
            "enabled": True,
        })
    if settings.deepseek_api_key:
        items.append({
            "id": "deepseek", "name": "DeepSeek",
            "logo": "deepseek", "type": "openai-compatible",
            "base_url": "https://api.deepseek.com/v1",
            "has_api_key": True,
            "enabled": True,
        })
    _BUILTIN_PROVIDERS = items

_init_builtin()

# ── 请求模型 ──
class CreateProviderRequest(BaseModel):
    name: str
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str
    api_key: str
    enabled: bool = True

class UpdateProviderRequest(BaseModel):
    name: str | None = None
    logo: str = ""
    type: str = "openai-compatible"
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None

# ── 辅助函数 ──
def _to_dict(p: Provider) -> dict:
    return {
        "id": p.provider_id,
        "name": p.name,
        "logo": p.logo,
        "type": p.type,
        "base_url": p.base_url,
        "has_api_key": bool(p.api_key_encrypted),
        "enabled": p.enabled,
        "created_at": str(p.created_at),
        "updated_at": str(p.updated_at),
    }

def _get_api_key(provider_id: str, db=None) -> str:
    """获取 Provider 的 API Key（先查内置，再查 DB）"""
    for bp in _BUILTIN_PROVIDERS:
        if bp["id"] == provider_id:
            if provider_id == "tongyi": return settings.tongyi_api_key
            if provider_id == "deepseek": return settings.deepseek_api_key
    if db:
        p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if p: return p.api_key_encrypted
    return ""

# ── API 接口 ──
@router.get("")
async def list_providers(db: Session = Depends(get_db)):
    """获取 Provider 列表（内置 + 自定义）"""
    custom = db.query(Provider).all()
    items = list(_BUILTIN_PROVIDERS)
    for p in custom:
        items.append(_to_dict(p))
    return ApiResponse(data={"items": items})

@router.get("/{provider_id}")
async def get_provider(provider_id: str, db: Session = Depends(get_db)):
    for bp in _BUILTIN_PROVIDERS:
        if bp["id"] == provider_id:
            return ApiResponse(data=bp)
    p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    return ApiResponse(data=_to_dict(p))

@router.post("")
async def create_provider(req: CreateProviderRequest, db: Session = Depends(get_db)):
    new_id = str(uuid.uuid4())[:8]
    p = Provider(
        provider_id=new_id,
        name=req.name,
        logo=req.logo,
        type=req.type,
        base_url=req.base_url,
        api_key_encrypted=req.api_key,
        enabled=req.enabled,
    )
    db.add(p)
    db.commit()
    return ApiResponse(data={"id": new_id})

@router.put("/{provider_id}")
async def update_provider(provider_id: str, req: UpdateProviderRequest, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    if req.name is not None: p.name = req.name
    if req.logo: p.logo = req.logo
    if req.type: p.type = req.type
    if req.base_url is not None: p.base_url = req.base_url
    if req.api_key is not None: p.api_key_encrypted = req.api_key
    if req.enabled is not None: p.enabled = req.enabled
    db.commit()
    return ApiResponse(data={"updated": True})

@router.delete("/{provider_id}")
async def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    db.delete(p)
    db.commit()
    return ApiResponse(data={"deleted": True})

@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, db: Session = Depends(get_db)):
    """\u6d4b\u8bd5\u8fde\u63a5\uff08\u771f\u5b9e\u8c03\u7528 Provider API\uff09"""
    api_key = _get_api_key(provider_id, db)
    base_url = ""
    for bp in _BUILTIN_PROVIDERS:
        if bp["id"] == provider_id:
            base_url = bp["base_url"]
            ptype = bp["type"]
            break
    else:
        p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if not p:
            raise HTTPException(404, "Provider not found")
        base_url = p.base_url
        ptype = p.type
    if not api_key:
        return ApiResponse(code=1, message="API Key \u672a\u914d\u7f6e", data={"ok": False})
    import time
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            t0 = time.time()
            if ptype == "tongyi":
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "qwen-plus", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
                )
            else:
                resp = await client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            latency = int((time.time() - t0) * 1000)
            return ApiResponse(data={"ok": True, "latency_ms": latency})
    except httpx.TimeoutException:
        return ApiResponse(code=1, message="\u8fde\u63a5\u8d85\u65f6", data={"ok": False})
    except httpx.HTTPStatusError as e:
        return ApiResponse(code=1, message=f"API \u8fd4\u56de\u9519\u8bef\u7801 {e.response.status_code}", data={"ok": False})
    except Exception as e:
        return ApiResponse(code=1, message=f"\u8fde\u63a5\u5931\u8d25: {str(e)[:100]}", data={"ok": False})

@router.get("/{provider_id}/remote-models")
async def remote_models(provider_id: str, db: Session = Depends(get_db)):
    """\u83b7\u53d6\u8fdc\u7a0b\u6a21\u578b\u5217\u8868\uff08\u901a\u8fc7 Provider \u7684\u771f\u5b9e API \u83b7\u53d6\uff09"""
    api_key = _get_api_key(provider_id, db)
    base_url = ""
    for bp in _BUILTIN_PROVIDERS:
        if bp["id"] == provider_id:
            base_url = bp["base_url"]; break
    else:
        p = db.query(Provider).filter(Provider.provider_id == provider_id).first()
        if p: base_url = p.base_url
    if not api_key:
        return ApiResponse(code=1, message="API Key \u672a\u914d\u7f6e", data={"models": []})
    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
            resp = await client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            data = resp.json()
        raw_list = data if isinstance(data, list) else data.get("data", [])
        models = []
        for m in raw_list:
            if isinstance(m, dict) and m.get("id"):
                models.append({"id": m["id"], "display_name": m.get("display_name", m["id"])})
        return ApiResponse(data={"models": models})
    except Exception as e:
        return ApiResponse(code=1, message=str(e)[:100], data={"models": []})
