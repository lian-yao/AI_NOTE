"""
平台接入 API：Cookie 管理。
用户在前端设置页粘贴 Cookie 字符串 → 后端持久化 → pipeline 实时读取。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.cookie_store import get_cookie, set_cookie

router = APIRouter(prefix="/platforms", tags=["platforms"])


class CookieUpdate(BaseModel):
    cookie: str


@router.get("/{platform}/cookie")
async def get_platform_cookie(platform: str):
    """获取平台 Cookie。"""
    cookie = get_cookie(platform) or ""
    return {
        "code": 0,
        "message": "success",
        "data": {
            "platform": platform,
            "cookie": cookie,
        },
    }


@router.put("/{platform}/cookie")
async def update_platform_cookie(platform: str, body: CookieUpdate):
    """更新平台 Cookie。"""
    set_cookie(platform, body.cookie)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "platform": platform,
            "cookie": body.cookie,
        },
    }
