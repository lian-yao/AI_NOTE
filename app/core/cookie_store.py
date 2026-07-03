"""
平台 Cookie 运行时存储。
供 API 端点 和 processor 模块共用，避免循环引用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


# 持久化文件（data/platform_cookies.json，data/ 已在 .gitignore）
_PERSIST_FILE = os.path.join("data", "platform_cookies.json")

# 内存缓存
_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    if not os.path.isfile(_PERSIST_FILE):
        return {}
    try:
        with open(_PERSIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(_PERSIST_FILE) or ".", exist_ok=True)
    with open(_PERSIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_cookie(platform: str) -> str | None:
    """获取平台 cookie 字符串。"""
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache.get(platform)


def set_cookie(platform: str, cookie: str) -> None:
    """设置平台 cookie 字符串并持久化。"""
    global _cache
    if _cache is None:
        _cache = _load()
    _cache[platform] = cookie
    _save(_cache)
