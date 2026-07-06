"""
音频提取器：使用 ffmpeg 从视频中提取音频（16kHz, mono, WAV）。
改用同步 subprocess + to_thread 以兼容 Windows SelectorEventLoop。
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.processor.retry import retry_with_backoff
from app.processor.storage import load_meta_json
from app.schemas.stage import StageResult

# ffmpeg 时间解析正则: HH:MM:SS.ms
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+.\d+)")


def _parse_ffmpeg_time(line: str) -> float:
    """将 ffmpeg 的 time=HH:MM:SS.ms 转为秒数。"""
    m = _TIME_RE.search(line)
    if not m:
        return 0.0
    h, minute, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + minute * 60 + s


def _ffprobe_duration(video_path: str) -> float:
    """同步调用 ffprobe 获取视频时长（秒）。失败返回 0。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def _extract_audio_sync(
    video_path: str,
    audio_path: str,
    sample_rate: int,
    duration_sec: float,
    progress_cb: Callable[[float], None] | None = None,
) -> None:
    """同步执行 ffmpeg 提取音频，通过回调报告进度。"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                      # 无视频流
        "-acodec", "pcm_s16le",     # 16-bit PCM
        "-ar", str(sample_rate),    # 采样率
        "-ac", "1",                 # mono
        audio_path,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    last_pct = 0
    # 从 stderr 读取进度（ffmpeg 进度输出到 stderr）
    for raw_line in proc.stderr:
        line = raw_line.decode("utf-8", errors="replace")
        if "time=" in line and progress_cb and duration_sec > 0:
            current = _parse_ffmpeg_time(line)
            pct = (current / duration_sec) * 100.0
            if pct - last_pct >= 10:
                last_pct = pct
                progress_cb(min(pct, 99.0))

    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 退出码 {proc.returncode}")

    if progress_cb:
        progress_cb(100.0)


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
        candidates = list(video_dir_path.glob(f"*{ext}"))
        if candidates:
            video_path = str(max(candidates, key=lambda p: p.stat().st_size))
            break

    if video_path is None:
        return StageResult(success=False, error=f"在 {video_dir} 中未找到视频文件，请先执行 download")

    # 2. 计算时长（用于进度估算）
    duration_sec = await asyncio.to_thread(_ffprobe_duration, video_path)
    # 3. 输出路径
    audio_path = str(video_dir_path / "audio.wav")

    async def _do_extract():
        await asyncio.to_thread(
            _extract_audio_sync,
            video_path, audio_path, sample_rate, duration_sec, progress_cb,
        )

    try:
        await retry_with_backoff(_do_extract, max_retries=2, base_delay=5.0, backoff=1.0)
    except FileNotFoundError:
        return StageResult(
            success=False,
            error="ffmpeg 未安装或不在 PATH 中。请安装 ffmpeg 后重试。",
        )
    except Exception as exc:
        return StageResult(success=False, error=f"音频提取失败 ({type(exc).__name__}): {exc}")

    if not os.path.isfile(audio_path):
        return StageResult(success=False, error=f"音频提取后文件不存在: {audio_path}")

    return StageResult(
        success=True,
        artifacts={"audio_path": audio_path},
        metadata={"audio_duration_seconds": duration_sec, "sample_rate": sample_rate},
    )
