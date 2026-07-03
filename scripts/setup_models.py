"""
预下载 Whisper 模型，避免运行时等待。
首次 clone 项目后运行一次即可：
    python scripts/setup_models.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载 .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.environ.get("WHISPER_MODEL_SIZE", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")


def main():
    # cpu 用 int8，cuda 用 float16
    compute = "int8" if DEVICE == "cpu" else "float16"

    print(f"预下载 Whisper 模型: {MODEL} (device={DEVICE}, compute={compute})")
    print("请等待，首次下载可能需要几分钟...")

    from faster_whisper import WhisperModel
    WhisperModel(MODEL, device=DEVICE, compute_type=compute)
    print(f"✅ {MODEL} 模型就绪")


if __name__ == "__main__":
    main()
