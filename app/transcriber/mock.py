"""
Mock 转写实现。
"""
from pathlib import Path

from app.schemas.transcript import TranscriptResult, TranscriptSegment


class MockTranscriber:
    """返回固定示例文本的 Mock 转写器。"""

    async def transcribe(self, audio_path: Path) -> TranscriptResult:
        return TranscriptResult(
            segments=[
                TranscriptSegment(text="人工智能正在改变世界。", start=0.0, end=2.5, confidence=0.98),
                TranscriptSegment(text="深度学习让计算机能够理解图像和语言。", start=2.5, end=5.0, confidence=0.95),
                TranscriptSegment(text="未来十年将有更多突破性进展。", start=5.0, end=7.0, confidence=0.97),
            ],
            full_text="人工智能正在改变世界。深度学习让计算机能够理解图像和语言。未来十年将有更多突破性进展。",
            language="zh",
            duration_seconds=7.0,
        )
