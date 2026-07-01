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
        import os

        from app.core.config import settings
        from app.core.paths import project_root

        opts = {
            "format": fmt,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_yt_dlp_hook],
            "socket_timeout": 30,
            "retries": 3,
        }

        # Cookie：用全局配置的 cookies.txt
        _cookie = settings.bilibili_cookie_file
        if _cookie:
            cookie_path = os.path.join(project_root(), _cookie) if not os.path.isabs(_cookie) else _cookie
            if os.path.isfile(cookie_path):
                opts["cookiefile"] = cookie_path

        loop = __import__("asyncio").get_running_loop()
        # yt-dlp 是同步库，在线程池中运行
        def _sync_download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        return await loop.run_in_executor(None, _sync_download)

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

    video_path = await retry_with_backoff(
        _do_download,
        max_retries=3,
        base_delay=5.0,
        backoff=5.0,
    )

    if not os.path.isfile(video_path):
        return StageResult(success=False, error=f"下载后文件不存在: {video_path}")

    return StageResult(
        success=True,
        artifacts={"video_path": video_path},
        metadata={"quality": quality},
    )
