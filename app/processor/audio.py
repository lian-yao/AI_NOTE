"""
音频提取器：使用 ffmpeg 从视频中提取音频（16kHz, mono, WAV）。
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path

from app.processor.retry import retry_with_backoff
from app.processor.storage import load_meta_json
from app.schemas.stage import StageResult

# ffmpeg 时间解析正则: HH:MM:SS.ms
_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+.\d+)")


def _is_valid_audio(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) > 44


def _safe_progress(progress_cb: Callable[[float], None] | None, pct: float) -> None:
    if not progress_cb:
        return
    try:
        progress_cb(pct)
    except Exception:
        pass


def _parse_ffmpeg_time(time_str: str) -> float:
    """将 ffmpeg 的 time=HH:MM:SS.ms 转为秒数。"""
    m = _TIME_RE.search(time_str)
    if not m:
        return 0.0
    h, minute, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + minute * 60 + s


def _probe_duration_sync(video_path: str) -> float:
    """读取视频时长。使用同步 subprocess，避开 Windows asyncio 子进程限制。"""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return 0.0
    return float(result.stdout.strip())


def _extract_audio_sync(
    cmd: list[str],
    audio_path: str,
    duration_sec: float,
    progress_cb: Callable[[float], None] | None,
) -> None:
    stderr_tail: deque[str] = deque(maxlen=20)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_pct = 0.0
    assert proc.stderr is not None
    for text in proc.stderr:
        clean_text = text.strip()
        if clean_text:
            stderr_tail.append(clean_text)
        if "time=" in text and progress_cb and duration_sec > 0:
            current = _parse_ffmpeg_time(text)
            pct = (current / duration_sec) * 100.0
            if pct - last_pct >= 10:
                last_pct = pct
                _safe_progress(progress_cb, min(pct, 99.0))

    proc.wait()

    if proc.returncode != 0:
        detail = "\n".join(stderr_tail)
        raise RuntimeError(f"ffmpeg 退出码 {proc.returncode}: {detail}")

    if not os.path.isfile(audio_path):
        raise RuntimeError(f"ffmpeg 未生成音频文件: {audio_path}")

    size = os.path.getsize(audio_path)
    if size <= 44:
        detail = "\n".join(stderr_tail)
        raise RuntimeError(f"ffmpeg 输出音频为空: {audio_path} ({size} bytes)\n{detail}")

    _safe_progress(progress_cb, 100.0)


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
        duration_sec = await asyncio.to_thread(_probe_duration_sync, video_path)
    except Exception:
        pass  # 获取时长失败不阻塞

    # 3. 输出路径
    audio_path = str(video_dir_path / "audio.wav")
    if _is_valid_audio(audio_path):
        _safe_progress(progress_cb, 100.0)
        return StageResult(
            success=True,
            artifacts={"audio_path": audio_path},
            metadata={"audio_duration_seconds": duration_sec, "sample_rate": sample_rate, "reused": True},
        )

    async def _do_extract():
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-i", video_path,
            "-map", "0:a:0",
            "-vn",                      # 无视频流
            "-acodec", "pcm_s16le",     # 16-bit PCM
            "-ar", str(sample_rate),    # 采样率
            "-ac", "1",                 # mono
            audio_path,
        ]

        await asyncio.to_thread(
            _extract_audio_sync,
            cmd,
            audio_path,
            duration_sec,
            progress_cb,
        )

    try:
        await retry_with_backoff(_do_extract, max_retries=2, base_delay=5.0, backoff=1.0)
    except FileNotFoundError:
        return StageResult(
            success=False,
            error="ffmpeg 未安装或不在 PATH 中。请安装 ffmpeg 后重试。",
        )
    except Exception as exc:
        if _is_valid_audio(audio_path):
            _safe_progress(progress_cb, 100.0)
            return StageResult(
                success=True,
                artifacts={"audio_path": audio_path},
                metadata={
                    "audio_duration_seconds": duration_sec,
                    "sample_rate": sample_rate,
                    "reused_after_error": True,
                    "warning": str(exc) or type(exc).__name__,
                },
            )
        detail = str(exc) or type(exc).__name__
        return StageResult(success=False, error=f"音频提取失败: {detail}")

    if not _is_valid_audio(audio_path):
        return StageResult(success=False, error=f"音频提取后文件不存在: {audio_path}")

    return StageResult(
        success=True,
        artifacts={"audio_path": audio_path},
        metadata={"audio_duration_seconds": duration_sec, "sample_rate": sample_rate},
    )
