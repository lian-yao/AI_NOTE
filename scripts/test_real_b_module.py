# 简化版：逐步验证 B 模块真实逻辑
import asyncio, sys, os, json, shutil
sys.path.insert(0, ".")

async def test_parse():
    from app.processor.parser import parse_bilibili_url
    url = "https://www.bilibili.com/video/BV1v57q6gEN9?vd_source=65008923e2b02f87786ff1b6d1453e11"
    print(">>> 测试 1: parse_bilibili_url (真实网络请求)")
    result = await parse_bilibili_url(url, "./data")
    print("  success:", result.success)
    print("  error:", result.error)
    if not result.success:
        return None
    print("  video_id:", result.metadata.get("video_id"))
    print("  title:", result.metadata.get("title"))
    print("  uploader:", result.metadata.get("uploader"))
    print("  duration:", result.metadata.get("duration_seconds"), "s")
    meta_path = result.artifacts.get("meta_json", "")
    if meta_path and os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
            print("  description:", (meta.get("description") or "")[:80])
            print("  uploader_uid:", meta.get("uploader_uid"))
    return result

async def test_download(video_dir):
    from app.processor.downloader import download_video
    print("\n>>> 测试 2: download_video (真实下载)")
    log = []
    result = await download_video(video_dir, quality="360p", progress_cb=lambda p: log.append(p))
    print("  success:", result.success)
    print("  error:", result.error)
    if result.success:
        print("  video_path:", result.artifacts.get("video_path"))
        print("  file_size:", result.metadata.get("file_size"))
        print("  progress callbacks:", len(log))
    return result

async def test_extract_audio(video_dir):
    from app.processor.audio import extract_audio
    print("\n>>> 测试 3: extract_audio (ffmpeg)")
    result = await extract_audio(video_dir)
    print("  success:", result.success)
    print("  error:", result.error)
    if result.success:
        print("  audio_path:", result.artifacts.get("audio_path"))
        print("  duration:", result.metadata.get("audio_duration_seconds"))
    return result

async def main():
    print("=" * 50)
    print("B 模块真实逻辑测试")
    print("=" * 50)

    r1 = await test_parse()
    if not r1:
        print("\n!! 解析失败，请检查网络或 B 站是否可访问")
        return

    video_id = r1.metadata.get("video_id", "")
    video_dir = os.path.abspath("./data/videos/" + video_id)
    print("  产物目录:", video_dir)

    # 下载（限制360p加速）
    r2 = await test_download(video_dir)
    if not (r2 and r2.success):
        print("\n!! 下载失败，跳过后续")
        return

    # 音频提取
    r3 = await test_extract_audio(video_dir)
    if not (r3 and r3.success):
        print("\n!! 音频提取失败")
        return

    print("\n\n>>> 三个 B 模块函数全部测试通过")
    print("    URL解析 ✓  下载 ✓  音频提取 ✓")

    # 清理
    shutil.rmtree(video_dir, ignore_errors=True)
    print("  产物已清理")

asyncio.run(main())
