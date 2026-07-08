"""
B 站视频链接解析器。

支持 BV 号、AV 号、b23.tv 短链接格式。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.processor.storage import ensure_video_dir, save_meta_json
from app.schemas.stage import StageResult


# B 站链接正则
_BV_PATTERN = re.compile(r"(?:bilibili\.com/(?:video/)?|bv:?)(BV[a-zA-Z0-9]{10})", re.I)
_AV_PATTERN = re.compile(r"(?:bilibili\.com/video/)?av(\d+)", re.I)
_SHORT_PATTERN = re.compile(r"b23\.tv/[a-zA-Z0-9]+", re.I)


def _extract_bvid(url: str) -> str | None:
    """从 URL 中提取 BV 号。"""

    m = _BV_PATTERN.search(url)
    return m.group(1) if m else None


def _extract_avid(url: str) -> int | None:
    """从 URL 中提取 AV 号。"""
    m = _AV_PATTERN.search(url)
    return int(m.group(1)) if m else None


def _is_short_url(url: str) -> bool:
    """判断是否为 b23.tv 短链接。"""
    return bool(_SHORT_PATTERN.search(url))


def _build_video_id(bvid: str | None, avid: int | None) -> str:
    """根据 BV/AV 号生成系统内部 video_id。"""
    if bvid:
        return f"b_{bvid}"
    if avid:
        return f"av_{avid}"
    raise ValueError("无法从链接中提取 BV 号或 AV 号")


async def parse_bilibili_url(
    url: str,
    base_data_dir: str = "./data",
    cookie: str | None = None,
) -> StageResult:
    """解析 B 站视频链接，提取元数据并保存到 meta.json。

    使用 yt-dlp 的 extract_info 获取完整元数据（标题、UP 主、封面等）。

    Args:
        url: B 站视频链接
        base_data_dir: 数据根目录
        cookie: B 站 Cookie 字符串（如 "SESSDATA=xxx; sid=xxx"），
                或 cookies.txt 文件路径。
                B 站 API 要求登录态，不提供会返回 HTTP 412。

    Returns:
        StageResult:
            - .artifacts["meta_json"] = meta.json 路径
            - .metadata 含 video_id, title, uploader, bvid, avid 等

    Raises:
        ImportError: yt-dlp 未安装
        yt_dlp.utils.DownloadError: 网络问题或 B 站限流
    """
    # 1. 提取 ID
    bvid = _extract_bvid(url)
    avid = _extract_avid(url)

    # 2. 用 yt-dlp 获取元数据
    import yt_dlp
    import os

    from app.core.paths import project_root

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }

    # Cookie：优先用显式传入的，否则用全局配置（浏览器提取 or 文件 or 字符串）
    if cookie:
        cookie_path = os.path.join(project_root(), cookie) if not os.path.isabs(cookie) else cookie
        if os.path.isfile(cookie_path):
            opts["cookiefile"] = cookie_path
    else:
        from app.processor import build_cookie_opts
        opts.update(build_cookie_opts())

    # 提取内部标记（yt-dlp 不认识这些 key）
    browser_cache_path = opts.pop("_browser_cache", None)
    _temp_cookie = opts.pop("_temp_cookie", False)
    uses_browser_cookie = "cookiesfrombrowser" in opts

    def _extract_info(extract_opts: dict):
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            video_info = ydl.extract_info(url, download=False)

            # 首次从浏览器提取成功 → 自动缓存到文件，后续直接复用
            if browser_cache_path and ydl.cookiejar:
                from app.processor import save_browser_cookies_to_cache
                try:
                    save_browser_cookies_to_cache(browser_cache_path, ydl.cookiejar)
                except Exception:
                    pass
            return video_info

    try:
        try:
            info = _extract_info(opts)
        except Exception as exc:
            from app.processor import (
                format_ytdlp_error,
                is_browser_cookie_error,
                without_browser_cookie_opts,
            )

            if uses_browser_cookie and is_browser_cookie_error(exc):
                try:
                    info = _extract_info(without_browser_cookie_opts(opts))
                except Exception as retry_exc:
                    return StageResult(
                        success=False,
                        error=(
                            "读取浏览器 Cookie 失败，已自动改为无 Cookie 解析但仍失败："
                            f"{format_ytdlp_error(retry_exc)}"
                        ),
                    )
            else:
                return StageResult(success=False, error=f"视频解析失败: {format_ytdlp_error(exc)}")
    finally:
        # string 模式：删除临时 cookie 文件
        if _temp_cookie:
            from app.processor import cleanup_temp_cookie
            cleanup_temp_cookie({"cookiefile": opts.get("cookiefile"), "_temp_cookie": True})

    if info is None:
        return StageResult(
            success=False,
            error="无法获取视频信息，请检查链接是否有效",
        )

    # 处理 playlist 情况
    if info.get("_type") == "playlist" and info.get("entries"):
        entries = info["entries"]
        # 尝试通过 p 参数匹配具体分P
        import urllib.parse
        parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        try:
            target_p = int((parsed_qs.get("p") or ["1"])[0])
        except (ValueError, IndexError):
            target_p = 1
        if 1 <= target_p <= len(entries):
            info = entries[target_p - 1]
        else:
            info = entries[0] if entries else info

    title = info.get("title", "未知标题")
    uploader = info.get("uploader") or info.get("channel") or ""
    uploader_id = str(info.get("uploader_id", "") or info.get("channel_id", "") or "")
    duration = info.get("duration") or 0
    cover_url = info.get("thumbnail") or ""
    description = info.get("description") or ""
    resolved_bvid = bvid or _extract_bvid(info.get("webpage_url", "") or info.get("original_url", "") or "")
    resolved_avid = avid or _extract_avid(info.get("webpage_url", "") or info.get("original_url", "") or "")

    video_id = _build_video_id(resolved_bvid, resolved_avid)
    if (resolved_bvid or resolved_avid) and "p=" in url:
        import urllib.parse
        parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        try:
            p_val = int((parsed_qs.get("p") or ["1"])[0])
            if p_val > 1:
                video_id = f"{video_id}_p{p_val}"
        except (ValueError, IndexError):
            pass

    # =========================================================================
    # 备用降级逻辑（yt-dlp 不可用时启用）：
    #
    # try:
    #     import yt_dlp
    #     ...  # 上面的正常流程
    # except ImportError:
    #     pass  # yt-dlp 未安装
    # except Exception:
    #     pass  # yt-dlp 调用失败（网络/B站限流等）
    #
    # if not yt_dlp_ok:
    #     resolved_bvid = bvid
    #     resolved_avid = avid
    #     video_id = _build_video_id(resolved_bvid, resolved_avid)
    #     title = f"视频 {video_id}"
    #     uploader = ""
    #     uploader_id = ""
    #     duration = 0
    #     cover_url = ""
    #     description = ""
    # =========================================================================

    # 3. 创建目录并保存 meta.json
    video_dir = ensure_video_dir(video_id, base_data_dir)
    meta = {
        "video_id": video_id,
        "url": url,
        "title": title,
        "uploader": uploader,
        "uploader_uid": uploader_id,
        "duration_seconds": int(duration) if duration else None,
        "cover_url": cover_url,
        "description": description or "",
        "bvid": resolved_bvid,
        "avid": resolved_avid,
    }
    meta_path = save_meta_json(video_dir, meta)

    return StageResult(
        success=True,
        artifacts={"meta_json": str(meta_path)},
        metadata={
            "video_id": video_id,
            "title": title,
            "uploader": uploader,
            "uploader_uid": uploader_id,
            "description": description or "",
            "duration_seconds": duration,
            "cover_url": cover_url,
            "bvid": resolved_bvid,
            "avid": resolved_avid,
        },
    )
