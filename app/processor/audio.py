"""
音频提取器：使用 ffmpeg 从视频中提取音频（16kHz, mono, WAV）。
"""
from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from pathlib import Path

from app.processor.retry import retry_with_backoff
from app.processor.storage import load_meta_json
from app.schemas.stage import StageResult

# ffmpeg 时间解析正则: HH:MM:SS.ms
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+.\d+)")


def _parse_ffmpeg_time(time_str: str) -> float:
    """将 ffmpeg 的 time=HH:MM:SS.ms 转为秒数。"""
    m = _TIME_RE.search(time_str)
    if not m:
        return 0.0
    h, minute, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + minute * 60 + s


async def extract_audio(
    video_dir: str,
    progress_cb: Callable[[float], None] | None = None,
    sample_rate: int = 16000,
) -> StageResult:
    """从视频中提取音频（16kHz, mono, PCM/WAV）。

    Args:
        video_dir: 产物目录（从中找到视频文件）
        progress_cb: 可选进度回调
        sample_rate: 采样率（默认 16000）

    Returns:
        StageResult:
            - .artifacts["audio_path"] = 提取的音频文件路径
    """
    video_dir_path = Path(video_dir)

    # 1. 找到视频文件
    video_path: str | None = None
    for ext in (".mp4", ".mkv", ".flv", ".webm", ".avi"):
        # 先按 meta.json 中的视频路径找，再扫描目录
        candidates = list(video_dir_path.glob(f"*{ext}"))
        if candidates:
            # 找最大的文件（很可能是视频）
            video_path = str(max(candidates, key=lambda p: p.stat().st_size))
            break

    if video_path is None:
        return StageResult(success=False, error=f"在 {video_dir} 中未找到视频文件，请先执行 download")

    # 2. 计算时长（用于进度估算）
    duration_sec = 0.0
    try:
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        if stdout:
            duration_sec = float(stdout.decode().strip())
    except Exception:
        pass  # 获取时长失败不阻塞

    # 3. 输出路径
    audio_path = str(video_dir_path / "audio.wav")

    async def _do_extract():
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn",                      # 无视频流
            "-acodec", "pcm_s16le",     # 16-bit PCM
            "-ar", str(sample_rate),    # 采样率
            "-ac", "1",                 # mono
            audio_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        last_pct = 0
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if "time=" in text and progress_cb and duration_sec > 0:
                current = _parse_ffmpeg_time(text)
                pct = (current / duration_sec) * 100.0
                if pct - last_pct >= 10:
                    last_pct = pct
                    progress_cb(min(pct, 99.0))

        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 退出码 {proc.returncode}")

        if progress_cb:
            progress_cb(100.0)

    try:
        await retry_with_backoff(_do_extract, max_retries=2, base_delay=5.0, backoff=1.0)
    except FileNotFoundError:
        return StageResult(
            success=False,
            error="ffmpeg 未安装或不在 PATH 中。请安装 ffmpeg 后重试。",
        )
    except Exception as exc:
        return StageResult(success=False, error=f"音频提取失败: {exc}")

    if not os.path.isfile(audio_path):
        return StageResult(success=False, error=f"音频提取后文件不存在: {audio_path}")

    return StageResult(
        success=True,
        artifacts={"audio_path": audio_path},
        metadata={"audio_duration_seconds": duration_sec, "sample_rate": sample_rate},
    )
