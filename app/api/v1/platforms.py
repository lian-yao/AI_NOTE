"""
平台接入 API：Cookie 管理。
用户在前端设置页粘贴 Cookie 字符串 → 后端持久化 → pipeline 实时读取。
"""
import asyncio
import os
import re
import shutil
import subprocess
import sys
from http.cookies import SimpleCookie
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.core.cookie_store import get_cookie, set_cookie

router = APIRouter(prefix="/platforms", tags=["platforms"])


class CookieUpdate(BaseModel):
    cookie: str


class CookieValidateRequest(BaseModel):
    cookie: str | None = None


class CookieImportBrowserRequest(BaseModel):
    browser: str | None = None
    save: bool = True


class LoginBrowserRequest(BaseModel):
    browser: str | None = None
    url: str | None = None


class QrCodePollRequest(BaseModel):
    qrcode_key: str
    save: bool = True


_BROWSER_CHOICES = {"chrome", "edge", "firefox", "brave", "opera", "chromium", "vivaldi"}
_BILIBILI_LOGIN_URL = "https://passport.bilibili.com/login"
_BILIBILI_QRCODE_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_BILIBILI_QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_BILIBILI_QRCODE_EXPIRES_IN = 180
_BILIBILI_QRCODE_POLL_INTERVAL = 2
_BILIBILI_COOKIE_PRIORITY = [
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
    "buvid3",
    "buvid4",
    "b_nut",
    "CURRENT_FNVAL",
]
_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_WINDOWS_BROWSER_PATHS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
        r"C:\Program Files\Opera\opera.exe",
    ],
    "chromium": [
        r"C:\Program Files\Chromium\Application\chrome.exe",
        r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
    ],
    "vivaldi": [
        os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
        r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
    ],
}

_BROWSER_COMMANDS = {
    "edge": ["msedge"],
    "chrome": ["chrome", "google-chrome"],
    "firefox": ["firefox"],
    "brave": ["brave", "brave-browser"],
    "opera": ["opera"],
    "chromium": ["chromium", "chromium-browser"],
    "vivaldi": ["vivaldi"],
}


def _browser_from_request(value: str | None) -> str:
    browser = (value or settings.bilibili_cookie_browser or "chrome").strip().lower()
    return browser


def _clean_error_text(value: Exception | str) -> str:
    text = _ANSI_PATTERN.sub("", str(value)).strip()
    return re.sub(r"\s+", " ", text)


def _browser_executable(browser: str) -> str | None:
    for command in _BROWSER_COMMANDS.get(browser, []):
        found = shutil.which(command)
        if found:
            return found

    if sys.platform.startswith("win"):
        for candidate in _WINDOWS_BROWSER_PATHS.get(browser, []):
            expanded = os.path.expandvars(candidate)
            if os.path.isfile(expanded):
                return expanded

    return None


def _open_url_in_browser(browser: str, url: str) -> None:
    executable = _browser_executable(browser)
    if not executable:
        raise FileNotFoundError(f"未找到 {browser} 浏览器可执行文件")
    subprocess.Popen(
        [executable, url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _format_browser_import_error(browser: str, exc: Exception) -> str:
    text = _clean_error_text(exc)
    if "dpapi" in text.lower() or "failed to decrypt" in text.lower():
        return (
            f"读取 {browser} Cookie 失败：浏览器 Cookie 由 Windows DPAPI/应用绑定加密保护，"
            "当前后端进程无法解密。请确认后端和浏览器使用同一 Windows 用户运行；"
            "如果仍失败，请在该浏览器里使用 Cookie 导出插件复制 Cookie，或改用其他浏览器同步。"
        )
    return f"读取 {browser} Cookie 失败：{text[:200]}"


def _cookiejar_to_cookie_string(cookiejar) -> str:
    rows: list[tuple[int, int, str, str]] = []
    priority = {name.lower(): index for index, name in enumerate(_BILIBILI_COOKIE_PRIORITY)}

    for cookie in cookiejar:
        domain = (getattr(cookie, "domain", "") or "").lstrip(".").lower()
        if not (domain == "bilibili.com" or domain.endswith(".bilibili.com")):
            continue
        if hasattr(cookie, "is_expired") and cookie.is_expired():
            continue
        name = str(getattr(cookie, "name", "") or "").strip()
        value = str(getattr(cookie, "value", "") or "").strip()
        if not name or not value:
            continue
        rows.append((priority.get(name.lower(), len(priority)), -len(domain), name, value))

    deduped: dict[str, tuple[int, int, str, str]] = {}
    for row in sorted(rows):
        key = row[2]
        if key not in deduped:
            deduped[key] = row

    return "; ".join(f"{name}={value}" for _, _, name, value in deduped.values())


def _set_cookie_headers_to_cookie_string(headers: list[str]) -> str:
    rows: list[tuple[int, str, str]] = []
    priority = {name.lower(): index for index, name in enumerate(_BILIBILI_COOKIE_PRIORITY)}

    for header in headers:
        jar = SimpleCookie()
        try:
            jar.load(header)
        except Exception:
            continue
        for name, morsel in jar.items():
            value = str(morsel.value or "").strip()
            if not name or not value:
                continue
            rows.append((priority.get(name.lower(), len(priority)), name, value))

    deduped: dict[str, tuple[int, str, str]] = {}
    for row in sorted(rows):
        key = row[1]
        if key not in deduped:
            deduped[key] = row

    return "; ".join(f"{name}={value}" for _, name, value in deduped.values())


def _response_to_cookie_string(response: httpx.Response) -> str:
    cookie = _cookiejar_to_cookie_string(response.cookies.jar)
    header_cookie = _set_cookie_headers_to_cookie_string(response.headers.get_list("set-cookie"))
    if header_cookie and "SESSDATA=" in header_cookie and "SESSDATA=" not in cookie:
        return header_cookie
    return cookie or header_cookie


def _bilibili_headers(cookie: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": _BILIBILI_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _extract_bilibili_cookie_from_browser(browser: str) -> str:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "cookiesfrombrowser": (browser,),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return _cookiejar_to_cookie_string(ydl.cookiejar)


async def _validate_bilibili_cookie(cookie: str) -> dict[str, Any]:
    if not cookie.strip():
        return {
            "platform": "bilibili",
            "valid": False,
            "is_login": False,
            "message": "Cookie 为空",
        }

    headers = _bilibili_headers(cookie)
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


async def _start_bilibili_qrcode_login() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        response = await client.get(_BILIBILI_QRCODE_GENERATE_URL, headers=_bilibili_headers())
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else {}
    qrcode_key = str(data.get("qrcode_key") or "").strip() if isinstance(data, dict) else ""
    url = str(data.get("url") or "").strip() if isinstance(data, dict) else ""
    if payload.get("code") != 0 or not qrcode_key or not url:
        raise RuntimeError(str(payload.get("message") or "Bilibili 二维码生成失败"))

    return {
        "platform": "bilibili",
        "qrcode_key": qrcode_key,
        "url": url,
        "expires_in": _BILIBILI_QRCODE_EXPIRES_IN,
        "poll_interval": _BILIBILI_QRCODE_POLL_INTERVAL,
        "message": "二维码已生成",
    }


async def _poll_bilibili_qrcode_login(qrcode_key: str, save: bool) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        response = await client.get(
            _BILIBILI_QRCODE_POLL_URL,
            params={"qrcode_key": qrcode_key},
            headers=_bilibili_headers(),
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        login_code = data.get("code") if isinstance(data, dict) else None
        message = str(
            (data.get("message") if isinstance(data, dict) else None)
            or payload.get("message")
            or ""
        )

        if login_code == 0:
            cookie = _response_to_cookie_string(response)
            redirect_url = str(data.get("url") or "") if isinstance(data, dict) else ""
            if not cookie and redirect_url.startswith(("http://", "https://")):
                redirect_response = await client.get(redirect_url, headers=_bilibili_headers())
                cookie = _response_to_cookie_string(redirect_response)

            validation = await _validate_bilibili_cookie(cookie) if cookie else {
                "platform": "bilibili",
                "valid": False,
                "is_login": False,
                "message": "扫码已确认，但未收到登录 Cookie",
            }
            saved = False
            if save and cookie and "SESSDATA=" in cookie:
                set_cookie("bilibili", cookie)
                saved = True

            return {
                **validation,
                "platform": "bilibili",
                "qrcode_key": qrcode_key,
                "status": "confirmed",
                "login_code": login_code,
                "cookie": cookie,
                "saved": saved,
                "refresh_token": data.get("refresh_token") if isinstance(data, dict) else "",
                "url": redirect_url,
                "message": (
                    "扫码登录成功，Cookie 已保存"
                    if saved
                    else validation.get("message") or "扫码已确认"
                ),
            }

    status = "pending"
    if login_code == 86090:
        status = "scanned"
    elif login_code == 86038:
        status = "expired"
    elif login_code not in {86101, 86090, 86038}:
        status = "failed"

    return {
        "platform": "bilibili",
        "qrcode_key": qrcode_key,
        "status": status,
        "login_code": login_code,
        "valid": False,
        "is_login": False,
        "cookie": "",
        "saved": False,
        "message": message or (
            "请在 Bilibili 手机端确认登录"
            if status == "scanned"
            else "等待扫码"
            if status == "pending"
            else "二维码已过期"
            if status == "expired"
            else "二维码登录失败"
        ),
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


@router.post("/{platform}/qrcode/start")
async def start_platform_qrcode_login(platform: str):
    """生成平台扫码登录二维码会话。"""
    if platform.lower() != "bilibili":
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "qrcode_key": "",
                "url": "",
                "expires_in": 0,
                "poll_interval": _BILIBILI_QRCODE_POLL_INTERVAL,
                "message": "当前仅支持 Bilibili 扫码登录",
            },
        }

    try:
        data = await _start_bilibili_qrcode_login()
    except Exception as exc:
        data = {
            "platform": "bilibili",
            "qrcode_key": "",
            "url": "",
            "expires_in": 0,
            "poll_interval": _BILIBILI_QRCODE_POLL_INTERVAL,
            "message": f"生成 Bilibili 二维码失败：{_clean_error_text(exc)}",
        }

    return {
        "code": 0,
        "message": "success",
        "data": data,
    }


@router.post("/{platform}/qrcode/poll")
async def poll_platform_qrcode_login(platform: str, body: QrCodePollRequest):
    """轮询平台扫码登录状态，成功后自动保存 Cookie。"""
    if platform.lower() != "bilibili":
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "qrcode_key": body.qrcode_key,
                "status": "failed",
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": "当前仅支持 Bilibili 扫码登录",
            },
        }

    qrcode_key = body.qrcode_key.strip()
    if not qrcode_key:
        data = {
            "platform": "bilibili",
            "qrcode_key": "",
            "status": "failed",
            "valid": False,
            "is_login": False,
            "cookie": "",
            "saved": False,
            "message": "二维码会话为空，请重新生成二维码",
        }
    else:
        try:
            data = await _poll_bilibili_qrcode_login(qrcode_key, body.save)
        except Exception as exc:
            data = {
                "platform": "bilibili",
                "qrcode_key": qrcode_key,
                "status": "failed",
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": f"轮询 Bilibili 登录状态失败：{_clean_error_text(exc)}",
            }

    return {
        "code": 0,
        "message": "success",
        "data": data,
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


@router.post("/{platform}/cookie/import-browser")
async def import_platform_cookie_from_browser(platform: str, body: CookieImportBrowserRequest):
    """从本机浏览器读取平台 Cookie，验证通过后自动保存。"""
    if platform.lower() != "bilibili":
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": "当前仅支持 Bilibili 浏览器 Cookie 同步",
            },
        }

    browser = _browser_from_request(body.browser)
    if browser not in _BROWSER_CHOICES:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "browser": browser,
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": f"暂不支持的浏览器：{browser}",
            },
        }

    try:
        cookie = await asyncio.to_thread(_extract_bilibili_cookie_from_browser, browser)
    except Exception as exc:
        message = _format_browser_import_error(browser, exc)
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "browser": browser,
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": message,
            },
        }

    if not cookie:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "browser": browser,
                "valid": False,
                "is_login": False,
                "cookie": "",
                "saved": False,
                "message": f"未在 {browser} 中找到 Bilibili Cookie，请先用该浏览器登录 B 站",
            },
        }

    result = await _validate_bilibili_cookie(cookie)
    saved = False
    if body.save and result.get("valid"):
        set_cookie("bilibili", cookie)
        saved = True

    return {
        "code": 0,
        "message": "success",
        "data": {
            **result,
            "platform": "bilibili",
            "browser": browser,
            "cookie": cookie,
            "saved": saved,
            "message": (
                "已从浏览器同步并保存 Cookie"
                if saved
                else result.get("message") or "已读取 Cookie，但验证未通过"
            ),
        },
    }


@router.post("/{platform}/login-browser")
async def open_platform_login_browser(platform: str, body: LoginBrowserRequest):
    """使用指定浏览器打开平台登录页。"""
    if platform.lower() != "bilibili":
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "opened": False,
                "message": "当前仅支持打开 Bilibili 登录页",
            },
        }

    browser = _browser_from_request(body.browser)
    url = body.url or _BILIBILI_LOGIN_URL
    if browser not in _BROWSER_CHOICES:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "browser": browser,
                "url": url,
                "opened": False,
                "message": f"暂不支持的浏览器：{browser}",
            },
        }

    try:
        await asyncio.to_thread(_open_url_in_browser, browser, url)
    except Exception as exc:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "platform": platform,
                "browser": browser,
                "url": url,
                "opened": False,
                "message": _clean_error_text(exc),
            },
        }

    return {
        "code": 0,
        "message": "success",
        "data": {
            "platform": platform,
            "browser": browser,
            "url": url,
            "opened": True,
            "message": f"已用 {browser} 打开 Bilibili 登录页",
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
            "updated": True,
        },
    }
