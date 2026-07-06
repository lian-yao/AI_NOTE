"""
平台接入 API：Cookie 管理。
用户在前端设置页粘贴 Cookie 字符串 → 后端持久化 → pipeline 实时读取。
"""
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.cookie_store import get_cookie, set_cookie

router = APIRouter(prefix="/platforms", tags=["platforms"])


class CookieUpdate(BaseModel):
    cookie: str


class CookieValidateRequest(BaseModel):
    cookie: str | None = None


async def _validate_bilibili_cookie(cookie: str) -> dict[str, Any]:
    if not cookie.strip():
        return {
            "platform": "bilibili",
            "valid": False,
            "is_login": False,
            "message": "Cookie 为空",
        }

    headers = {
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                headers=headers,
            )
        payload = response.json()
    except Exception as exc:
        return {
            "platform": "bilibili",
            "valid": False,
            "is_login": False,
            "message": f"验证请求失败：{exc}",
        }

    data = payload.get("data") if isinstance(payload, dict) else {}
    is_login = bool(data.get("isLogin")) if isinstance(data, dict) else False
    vip = data.get("vipStatus") if isinstance(data, dict) else None
    return {
        "platform": "bilibili",
        "valid": is_login,
        "is_login": is_login,
        "username": data.get("uname") if isinstance(data, dict) else None,
        "mid": data.get("mid") if isinstance(data, dict) else None,
        "level": data.get("level_info", {}).get("current_level") if isinstance(data, dict) else None,
        "vip_status": vip,
        "vip_type": data.get("vipType") if isinstance(data, dict) else None,
        "message": "Cookie 有效，已登录" if is_login else str(payload.get("message") or "Cookie 未登录或已过期"),
    }


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


@router.post("/{platform}/cookie/validate")
async def validate_platform_cookie(platform: str, body: CookieValidateRequest):
    """验证平台 Cookie 是否可用，不把 Cookie 回传给前端。"""
    cookie = body.cookie if body.cookie is not None else (get_cookie(platform) or "")
    if platform.lower() != "bilibili":
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "valid": bool(cookie.strip()),
                "is_login": bool(cookie.strip()),
                "message": "当前平台仅做非空校验",
            },
        }

    result = await _validate_bilibili_cookie(cookie)
    return {
        "code": 0,
        "message": "success",
        "data": result,
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
            "updated": True,
        },
    }
