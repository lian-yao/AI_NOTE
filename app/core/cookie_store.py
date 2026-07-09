"""
平台 Cookie 运行时存储。
供 API 端点 和 processor 模块共用，避免循环引用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.paths import project_root


# 内存缓存
_cache: dict[str, str] | None = None


def _persist_file() -> Path:
    """Cookie 主存储路径，应跟随桌面端/服务端运行时数据目录。"""
    from app.core.config import settings

    return Path(settings.data_dir) / "platform_cookies.json"


def _legacy_persist_file() -> Path:
    """早期版本写到项目 data/ 下，保留读取兼容。"""
    return project_root() / "data" / "platform_cookies.json"


def _load() -> dict[str, str]:
    data: dict[str, str] = {}
    for persist_file in (_persist_file(), _legacy_persist_file()):
        if not persist_file.is_file():
            continue
        try:
            with persist_file.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(
                        {str(k): str(v) for k, v in loaded.items() if isinstance(v, str)}
                    )
        except (json.JSONDecodeError, OSError):
            pass

    for platform, cookie in _load_legacy_frontend_cookies().items():
        data.setdefault(platform, cookie)

    return data


def _load_legacy_frontend_cookies() -> dict[str, str]:
    """读取旧 frontend_config.json 中保存的平台 Cookie，兼容早期设置页路径。"""
    try:
        from app.core.config import settings

        legacy_file = Path(settings.data_dir) / "frontend_config.json"
        if not legacy_file.is_file():
            return {}

        raw = json.loads(legacy_file.read_text(encoding="utf-8"))
        cookies = raw.get("cookies") if isinstance(raw, dict) else None
        if not isinstance(cookies, dict):
            return {}

        return {str(k): str(v) for k, v in cookies.items() if isinstance(v, str)}
    except Exception:
        return {}


def _save(data: dict[str, str]) -> None:
    persist_file = _persist_file()
    os.makedirs(persist_file.parent, exist_ok=True)
    with persist_file.open("w", encoding="utf-8") as f:
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
