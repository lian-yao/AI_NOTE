"""
视频下载器：使用 yt-dlp 下载 B 站视频，支持画质选择与进度回调。
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from app.processor.retry import retry_with_backoff
from app.processor.storage import load_meta_json
from app.schemas.stage import StageResult


async def download_video(
    video_dir: str,
    quality: str = "1080p",
    progress_cb: Callable[[float], None] | None = None,
    base_data_dir: str = "./data",
) -> StageResult:
    """下载视频文件。

    从 video_dir/meta.json 读取 URL 和元数据，调用 yt-dlp 下载。

    Args:
        video_dir: 产物目录路径（含 meta.json）
        quality: 目标画质（360p/480p/720p/1080p）
        progress_cb: 可选进度回调，接收 0.0-100.0
        base_data_dir: 数据根目录

    Returns:
        StageResult:
            - .artifacts["video_path"] = 下载的视频文件路径
    """
    video_dir_path = Path(video_dir)

    # 读取元数据
    try:
        meta = load_meta_json(video_dir_path)
    except FileNotFoundError:
        return StageResult(success=False, error="meta.json 不存在，请先执行 parse")

    url = meta.get("url", "")
    if not url:
        return StageResult(success=False, error="meta.json 中缺少 url 字段")

    # 画质映射
    quality_map = {
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    }
    fmt = quality_map.get(quality, quality_map["1080p"])

    output_template = str(video_dir_path / "%(title)s.%(ext)s")
    media_extensions = {".mp4", ".m4v", ".mkv", ".webm", ".mov"}
    existing_media = [
        path for path in video_dir_path.iterdir()
        if path.is_file() and path.suffix.lower() in media_extensions
    ]
    if existing_media:
        video_path = str(max(existing_media, key=lambda path: path.stat().st_size))
        if progress_cb:
            progress_cb(100.0)
        return StageResult(
            success=True,
            artifacts={"video_path": video_path},
            metadata={
                "quality": quality,
                "file_size": os.path.getsize(video_path),
                "reused": True,
            },
        )

    # 进度追踪
    last_pct = 0

    def _yt_dlp_hook(d: dict):
        nonlocal last_pct
        if d["status"] == "downloading" and progress_cb:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100.0
                if pct - last_pct >= 5:  # 每 5% 回调一次
                    last_pct = pct
                    progress_cb(min(pct, 99.0))
        elif d["status"] == "finished" and progress_cb:
            progress_cb(100.0)

    async def _do_download() -> str:
        import yt_dlp

        opts = {
            "format": fmt,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_yt_dlp_hook],
            "socket_timeout": 30,
            "retries": 3,
        }

        # Cookie：用全局配置（设置页字符串 / 文件 / 显式浏览器读取）
        from app.processor import (
            build_cookie_opts,
            cleanup_temp_cookie,
            format_ytdlp_error,
            is_browser_cookie_error,
            save_browser_cookies_to_cache,
            without_browser_cookie_opts,
        )
        opts.update(build_cookie_opts())

        # 提取内部标记（yt-dlp 不认识这些 key）
        browser_cache_path = opts.pop("_browser_cache", None)
        _temp_cookie = opts.pop("_temp_cookie", False)
        uses_browser_cookie = "cookiesfrombrowser" in opts

        loop = __import__("asyncio").get_running_loop()
        # yt-dlp 是同步库，在线程池中运行
        def _sync_download_with(download_opts: dict):
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # 首次从浏览器提取成功 → 自动缓存
                if browser_cache_path and ydl.cookiejar:
                    try:
                        save_browser_cookies_to_cache(browser_cache_path, ydl.cookiejar)
                    except Exception:
                        pass
                prepared = Path(ydl.prepare_filename(info))
                if prepared.is_file():
                    return str(prepared)

                candidates = [
                    path for path in video_dir_path.iterdir()
                    if path.is_file() and path.suffix.lower() in media_extensions
                ]
                if candidates:
                    return str(max(candidates, key=lambda path: path.stat().st_mtime))
                return str(prepared)

        def _sync_download():
            try:
                return _sync_download_with(opts)
            except Exception as exc:
                if uses_browser_cookie and is_browser_cookie_error(exc):
                    try:
                        return _sync_download_with(without_browser_cookie_opts(opts))
                    except Exception as retry_exc:
                        raise RuntimeError(
                            "读取浏览器 Cookie 失败，已自动改为无 Cookie 下载但仍失败："
                            f"{format_ytdlp_error(retry_exc)}"
                        ) from retry_exc
                raise

        try:
            return await loop.run_in_executor(None, _sync_download)
        finally:
            # string 模式：删除临时 cookie 文件
            if _temp_cookie:
                cleanup_temp_cookie({"cookiefile": opts.get("cookiefile"), "_temp_cookie": True})

    # =========================================================================
    # 备用降级逻辑（画质不可用时启用）：
    #
    # except Exception as exc:
    #     if quality != "480p":
    #         try:
    #             return await download_video(video_dir, "480p", progress_cb, base_data_dir)
    #         except Exception:
    #             pass
    #     return StageResult(success=False, error=f"视频下载失败: {exc}")
    # =========================================================================

    try:
        video_path = await retry_with_backoff(
            _do_download,
            max_retries=3,
            base_delay=5.0,
            backoff=5.0,
        )
    except Exception as exc:
        from app.processor import format_ytdlp_error
        return StageResult(success=False, error=f"视频下载失败: {format_ytdlp_error(exc)}")

    if not os.path.isfile(video_path):
        return StageResult(success=False, error=f"下载后文件不存在: {video_path}")

    return StageResult(
        success=True,
        artifacts={"video_path": video_path},
        metadata={"quality": quality, "file_size": os.path.getsize(video_path)},
    )
