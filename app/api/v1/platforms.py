"""Platform-specific settings API (cookie management)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.core.cookie_store import get_cookie, set_cookie
from pydantic import BaseModel

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("/bilibili/cookie")
def get_bilibili_cookie():
    cookie = get_cookie("bilibili")
    if not cookie:
        from app.core.config import settings
        if settings.bilibili_cookie_file:
            import os
            if os.path.isfile(settings.bilibili_cookie_file):
                try:
                    with open(settings.bilibili_cookie_file, encoding="utf-8") as f:
                        cookie = f.read()
                except Exception:
                    pass
    return {"cookie": cookie or ""}


class CookieUpdate(BaseModel):
    cookie: str


@router.put("/bilibili/cookie")
def update_bilibili_cookie(body: CookieUpdate):
    set_cookie("bilibili", body.cookie)
    return {"status": "ok", "message": "Cookie saved"}
