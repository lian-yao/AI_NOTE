"""
处理器协议。

- VideoProcessor: 视频下载、音频提取（角色 B）
- Processor: 转录文本拆分为结构化文本块（角色 C 向量化前处理）
- build_cookie_opts: 根据配置构建 yt-dlp cookie 参数
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol

from app.schemas.chunk import ChunkBase
from app.schemas.stage import StageResult
from app.schemas.transcript import TranscriptResult

from app.processor.video_processor import BilibiliVideoProcessor

_BROWSER_COOKIE_ERROR_MARKERS = (
    "dpapi",
    "decrypt",
    "cookie database",
    "could not copy chrome cookie database",
    "browser cookies",
)


def _cookie_string_to_netscape(cookie_str: str, domain: str = ".bilibili.com") -> str:
    """将 Cookie 字符串转为 Netscape 格式文本。

    输入: "SESSDATA=xxx; bili_jct=yyy; buvid3=zzz"
    输出: Netscape HTTP Cookie File 格式（可用于 yt-dlp cookiefile）
    """
    import time

    lines = ["# Netscape HTTP Cookie File"]
    # 过期时间设为 2 年后
    far_future = int(time.time()) + 3600 * 24 * 730

    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if not name or not value:
            continue
        # Netscape 格式: domain  flag  path  secure  expiry  name  value
        # 关键登录 cookie 用 TRUE（secure），其他用 FALSE
        secure = "TRUE" if name.lower() in ("sessdata", "bili_jct", "sid") else "FALSE"
        lines.append(f"{domain}\tTRUE\t/\t{secure}\t{far_future}\t{name}\t{value}")

    return "\n".join(lines) + "\n"


# B站 API 要求的 HTTP 请求头，缺了会被 CDN/WAF 返回 412
_BILIBILI_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


def build_cookie_opts() -> dict:
    """根据全局配置构建 yt-dlp 的 cookie 相关参数。

    四种来源（VN_BILIBILI_COOKIE_SOURCE）：
    - "string":  从前端设置页提交的 Cookie 字符串读取（生产推荐）。
                 无本地明文文件，每次运行时转为临时 Netscape 文件。
    - "browser": 优先用缓存的 cookies.txt，没有时从浏览器提取并自动缓存。
    - "file":    仅从 cookies.txt 读取。
    - "none":    不使用 Cookie。

    Returns:
        dict: 可合并到 yt-dlp opts。
              _browser_cache  → browser 模式首次提取后需缓存
              _temp_cookie    → string 模式的临时文件，用完需删除
              http_headers    → B站要求的 UA/Referer，避免 412
    """
    import os
    import tempfile
    from app.core.config import settings
    from app.core.paths import project_root

    source = settings.bilibili_cookie_source
    if source not in {"string", "browser", "file", "none"}:
        source = "string"

    # 前端「设置 → 平台数据」保存的 Cookie 应优先生效。
    # 这样用户不需要额外改 VN_BILIBILI_COOKIE_SOURCE，也能让解析、下载和播放器共用登录态。
    if source != "none":
        from app.core.cookie_store import get_cookie as _get_stored_cookie
        cookie_str = _get_stored_cookie("bilibili")
        if cookie_str:
            netscape = _cookie_string_to_netscape(cookie_str)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", prefix="vn_cookie_", delete=False,
                encoding="utf-8",
            )
            tmp.write(netscape)
            tmp.close()
            return {
                "cookiefile": tmp.name,
                "_temp_cookie": True,
                "http_headers": _BILIBILI_HTTP_HEADERS,
            }

    # ── source: string ──────────────────────────────────────────────
    if source == "string":
        return {}

    # ── source: browser ─────────────────────────────────────────────
    elif source == "browser":
        _cookie = settings.bilibili_cookie_file
        if _cookie:
            cookie_path = os.path.join(project_root(), _cookie) if not os.path.isabs(_cookie) else _cookie
            if os.path.isfile(cookie_path):
                # 已有缓存 → 直接用文件
                return {"cookiefile": cookie_path, "http_headers": _BILIBILI_HTTP_HEADERS}
        # 无缓存 → 从浏览器提取，并标记需要缓存
        browser = settings.bilibili_cookie_browser or "chrome"
        default_cache = os.path.join(str(project_root()), "data", "cookies.txt")
        return {
            "cookiesfrombrowser": (browser,),
            "_browser_cache": _cookie or default_cache,
            "http_headers": _BILIBILI_HTTP_HEADERS,
        }

    # ── source: file ────────────────────────────────────────────────
    elif source == "file":
        _cookie = settings.bilibili_cookie_file
        if _cookie:
            cookie_path = os.path.join(project_root(), _cookie) if not os.path.isabs(_cookie) else _cookie
            if os.path.isfile(cookie_path):
                return {"cookiefile": cookie_path, "http_headers": _BILIBILI_HTTP_HEADERS}

    # source == "none" 或文件不存在
    return {}


def is_browser_cookie_error(exc: BaseException) -> bool:
    """判断 yt-dlp 异常是否来自浏览器 Cookie 读取/解密。"""
    message = str(exc).lower()
    return any(marker in message for marker in _BROWSER_COOKIE_ERROR_MARKERS)


def without_browser_cookie_opts(opts: dict) -> dict:
    """移除浏览器 Cookie 相关选项，保留其它 yt-dlp 配置。"""
    clean = dict(opts)
    clean.pop("cookiesfrombrowser", None)
    clean.pop("_browser_cache", None)
    return clean


_ANSI_PATTERN = __import__("re").compile(r"\x1b\[[0-9;]*m")


def format_ytdlp_error(exc: BaseException) -> str:
    """把 yt-dlp 的异常压成适合返回给前端的短消息。"""
    message = str(exc).strip()
    if not message:
        message = type(exc).__name__
    # 去除 ANSI 转义序列（如 [0;31m）
    message = _ANSI_PATTERN.sub("", message)
    message = message.replace("ERROR: ERROR:", "ERROR:").replace("ERROR:", "").strip()
    return message[:300]


def cleanup_temp_cookie(opts: dict) -> None:
    """删除 build_cookie_opts 创建的临时 cookie 文件。
    当 _temp_cookie 标记为 True 时，删除 cookiefile 指向的临时文件。
    """
    import os
    if not opts.get("_temp_cookie"):
        return
    temp_path = opts.get("cookiefile")
    if temp_path and os.path.isfile(temp_path):
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def save_browser_cookies_to_cache(cache_path: str, cookiejar) -> None:
    """将浏览器提取的 cookie 缓存到文件，下次直接复用，不再需要浏览器。

    Args:
        cache_path: 缓存文件路径（相对路径相对于项目根目录）
        cookiejar: yt-dlp 的 cookiejar 对象（ydl.cookiejar）
    """
    import os
    from app.core.paths import project_root

    path = os.path.join(project_root(), cache_path) if not os.path.isabs(cache_path) else cache_path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cookiejar.save(path)
    import logging
    logging.getLogger(__name__).info("Cookie 已缓存到 %s，后续将直接使用文件，不再读取浏览器", path)


class VideoProcessor(Protocol):
    """视频下载与音频提取接口（按团队分工文档 角色 B 3.2 节定义）。"""

    async def parse(self, url: str, video_dir: str) -> StageResult:
        """解析视频链接，提取元数据。

        Args:
            url: 视频链接（B 站 BV/AV/短链接）
            video_dir: 产物目录，解析结果写入 meta.json

        Returns:
            StageResult: .artifacts["meta_json"] 为 meta.json 路径
                         .metadata 含 video_id, title, uploader 等字段
        """
        ...

    async def download(
        self,
        video_dir: str,
        quality: str = "1080p",
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """下载视频文件。

        Args:
            video_dir: 产物目录（从中读取 meta.json 获取 URL）
            quality: 画质选择（360p/480p/720p/1080p）
            progress_cb: 可选进度回调，接收 0.0-100.0

        Returns:
            StageResult: .artifacts["video_path"] 为视频文件路径
        """
        ...

    async def extract_audio(
        self,
        video_dir: str,
        progress_cb: Callable[[float], None] | None = None,
    ) -> StageResult:
        """从视频中提取音频（16kHz, mono, WAV）。

        Args:
            video_dir: 产物目录（从中读取 video.mp4）
            progress_cb: 可选进度回调，接收 0.0-100.0

        Returns:
            StageResult: .artifacts["audio_path"] 为音频文件路径
        """
        ...


class Processor(Protocol):
    """对转录结果进行拆分、清洗、丰富，生成结构化文本块。"""

    async def process(
        self, transcript: TranscriptResult, note_id: int, video_id: str
    ) -> list[ChunkBase]:
        ...
