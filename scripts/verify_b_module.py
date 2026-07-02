"""验证 B 模块接管 Orchestrator 的流水线是否正常运行。"""
import asyncio
import sys
import tempfile
import shutil
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas.stage import StageResult
from app.processor import storage

# ── 打桩：模拟 B 模块函数，不调网络 ──

async def mock_parse(url, base_data_dir="./data", cookie=None):
    video_id = "b_BV1test123"
    vdir = Path(base_data_dir) / "videos" / video_id
    vdir.mkdir(parents=True, exist_ok=True)
    meta = {
        "video_id": video_id, "url": url, "title": "测试视频标题",
        "uploader": "测试UP主", "uploader_uid": "12345",
        "duration_seconds": 600, "cover_url": "",
        "description": "测试描述", "bvid": "BV1test123", "avid": None,
    }
    storage.save_meta_json(vdir, meta)
    return StageResult(
        success=True,
        artifacts={"meta_json": str(vdir / "meta.json"), "video_dir": str(vdir)},
        metadata={**meta, "video_dir": str(vdir)},
    )

async def mock_download(video_dir, quality="1080p", progress_cb=None, base_data_dir="./data"):
    if progress_cb:
        progress_cb(100.0)
    return StageResult(
        success=True,
        artifacts={"video_path": str(Path(video_dir) / "video.mp4")},
        metadata={"quality": quality, "file_size": 1024},
    )

async def mock_extract_audio(video_dir, progress_cb=None):
    if progress_cb:
        progress_cb(100.0)
    return StageResult(
        success=True,
        artifacts={"audio_path": str(Path(video_dir) / "audio.wav")},
        metadata={"audio_duration_seconds": 600, "sample_rate": 16000},
    )

# 替换 B 模块函数
import app.processor.parser as pmod
import app.processor.downloader as dmod
import app.processor.audio as amod
pmod.parse_bilibili_url = mock_parse
dmod.download_video = mock_download
amod.extract_audio = mock_extract_audio

# 打桩 LLM 客户端，避免 NoteGenerator 调真实 API
class _FlexibleMockLLM:
    async def chat(self, messages, **kwargs):
        return '# Test Note\n\nMock generated note content.'
    async def embed(self, texts, **kwargs):
        return [[0.1]*10 for _ in texts]
import app.llm.client
app.llm.client.get_llm_client = lambda: _FlexibleMockLLM()

from app.pipeline.orchestrator import PipelineOrchestrator

events_log = []

def on_event(ev):
    events_log.append(ev)
    print(f"  [{ev.event:>9}] {ev.stage:12s} {ev.progress:3d}% | {ev.message}")

async def main():
    tmpdir = tempfile.mkdtemp()
    os.environ["VN_DATA_DIR"] = tmpdir

    from app.core.database import engine, Base, SessionLocal
    Base.metadata.create_all(bind=engine)

    orch = PipelineOrchestrator()
    orch.on_progress(on_event)

    task = await orch.start_task("https://www.bilibili.com/video/BV1test123")
    print(f"\nTask {task.task_id} 已启动，等待完成...\n")

    while task.status in ("pending", "running"):
        await asyncio.sleep(0.05)

    print(f"\n=== 结果 ===")
    print(f"  状态:       {task.status}")
    print(f"  video_id:   {task.video_id}")
    print(f"  note_id:    {task.note_id}")
    print(f"  进度:       {task.progress}%")
    print(f"  错误:       {task.error}")
    print(f"  事件数:     {len(events_log)}")
    print()

    db = SessionLocal()
    try:
        from app.models.video import Video
        from app.models.note import Note
        v = db.query(Video).filter(Video.video_id == task.video_id).first()
        n = db.query(Note).filter(Note.id == task.note_id).first()
        if v:
            print(f"  数据库 video_id:    {v.video_id}")
            print(f"          title:      {v.title}")
            print(f"          uploader:   {v.uploader}")
            print(f"          status:     {v.status}")
            print(f"          video_path: {v.video_path}")
            print(f"          audio_path: {v.audio_path}")
        if n:
            print(f"  数据库 note_id:     {n.id}")
            print(f"          文件路径:   {n.file_path}")
            print(f"          摘要:       {n.summary[:40]}")
    finally:
        db.close()

    shutil.rmtree(tmpdir, ignore_errors=True)

    success = task.status == "completed" and task.video_id is not None and task.note_id is not None
    print(f"\n>>> 测试{'通过' if success else '失败'}: 流水线状态={task.status}")

asyncio.run(main())
