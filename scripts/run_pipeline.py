r"""
完整流水线：解析 → 下载 → 提取音频 → 语音转写。
直接运行即可，修改下方 URL 后点运行。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载 .env 到 os.environ（读取模型配置等）
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.processor.parser import parse_bilibili_url
from app.processor.downloader import download_video
from app.processor.audio import extract_audio
from app.transcriber.whisper import FasterWhisperTranscriber

# 从 .env 读取模型配置（与 Web 应用共享同一份配置）
WHISPER_MODEL = os.environ.get("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")

# ============================================================
#  改这里：B站视频链接
# ============================================================
URL = "https://www.bilibili.com/video/BV1vdyGBzEw3"
# ============================================================

# ============================================================
#  可选：画质 360p / 480p / 720p / 1080p
# ============================================================
QUALITY = "480p"
# ============================================================


def make_progress(label: str):
    def cb(pct: float) -> None:
        print(f'  {label}: {pct:.0f}%')
    return cb


async def run_pipeline(url: str, quality: str = "480p", data_dir: str = "") -> None:
    if not data_dir:
        from app.core.paths import project_root
        data_dir = str(project_root() / "data")
    print(f'目标: {url}')
    print(f'画质: {quality}  |  数据目录: {data_dir}')
    print()

    # 1. 解析
    print('=== 1. 解析视频链接 ===')
    result = await parse_bilibili_url(url, base_data_dir=data_dir)
    if not result.success:
        print(f'✗ 解析失败: {result.error}')
        return

    meta_json = result.artifacts['meta_json']
    video_dir = str(Path(meta_json).parent)
    print(f'  meta.json → {meta_json}')
    print(f'  标题: {result.metadata.get("title")}')
    print(f'  UP主: {result.metadata.get("uploader")}')
    duration = result.metadata.get("duration_seconds", 0)
    if duration:
        print(f'  时长: {duration}s ({duration // 60}分{duration % 60}秒)')

    # 2. 下载
    print()
    print(f'=== 2. 下载视频 ({quality}) ===')
    r = await download_video(
        video_dir, quality=quality,
        progress_cb=make_progress('下载'),
        base_data_dir=data_dir,
    )
    if not r.success:
        print(f'✗ 下载失败: {r.error}')
        return
    video_path = r.artifacts['video_path']
    file_size_mb = r.metadata.get('file_size', 0) / (1024 * 1024)
    print(f'  视频 → {video_path} ({file_size_mb:.1f} MB)')

    # 3. 提取音频
    print()
    print('=== 3. 提取音频 (ffmpeg) ===')
    r = await extract_audio(video_dir, progress_cb=make_progress('提取'))
    if not r.success:
        print(f'✗ 提取失败: {r.error}')
        return
    print(f'  音频 → {r.artifacts["audio_path"]}')
    print(f'  时长: {r.metadata.get("audio_duration_seconds", 0):.0f}s')
    print(f'  采样率: {r.metadata.get("sample_rate")}Hz')

    # 4. 语音转写
    print()
    print(f'=== 4. 语音转写 (Faster-Whisper {WHISPER_MODEL}) ===')
    transcriber = FasterWhisperTranscriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE)
    r = await transcriber.transcribe(
        r.artifacts["audio_path"], video_dir,
        progress_cb=make_progress('转写'),
    )
    if not r.success:
        print(f'✗ 转写失败: {r.error}')
        return
    print(f'  语言: {r.metadata.get("language")}')
    print(f'  片段数: {r.metadata.get("segment_count")}')
    print(f'  JSON → {r.artifacts["transcript_json"]}')
    print(f'  SRT  → {r.artifacts["transcript_srt"]}')
    full_text = r.metadata.get("full_text", "")
    print(f'  全文预览: {full_text[:200]}{"..." if len(full_text) > 200 else ""}')

    print()
    print(f'=== 全流程完成 ===')
    print(f'产物目录: {video_dir}')


if __name__ == '__main__':
    if not URL:
        print("❌ URL 为空，请先在脚本顶部填入 B站视频链接")
        sys.exit(1)
    asyncio.run(run_pipeline(URL, quality=QUALITY, data_dir=""))
    