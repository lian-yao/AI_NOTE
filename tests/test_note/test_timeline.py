from app.note.timeline import (
    build_timeline_sections_from_segments,
    extract_timeline_sections,
    seconds_from_timestamp,
    timeline_sections_have_ranges,
)
from app.store.chunker import semantic_chunk


def test_extract_timeline_sections_from_headings():
    markdown = """# Demo

## 内容分块
### 章节一：开场介绍（00:10 - 01:05）
介绍背景和问题。

### 章节二：方案拆解（01:05 - 03:00）
总结实现路径。
"""

    sections = extract_timeline_sections(markdown)

    assert sections == [
        {
            "title": "开场介绍",
            "start_time": 10,
            "end_time": 65,
            "content": "介绍背景和问题。",
            "chunk_index": 0,
        },
        {
            "title": "方案拆解",
            "start_time": 65,
            "end_time": 180,
            "content": "总结实现路径。",
            "chunk_index": 1,
        },
    ]


def test_extract_timeline_sections_from_bullets():
    markdown = "- [00:00 - 00:42] **核心观点**: 先提出结论，再解释原因。"

    assert extract_timeline_sections(markdown) == [
        {
            "title": "核心观点",
            "start_time": 0,
            "end_time": 42,
            "content": "先提出结论，再解释原因。",
            "chunk_index": 0,
        }
    ]


def test_semantic_chunk_keeps_timeline_boundaries():
    chunks = semantic_chunk(
        """## 内容分块
### 第一部分：真实片段（01:00 - 02:30）
这是该时间块的总结。
"""
    )

    assert chunks == [
        {
            "title": "真实片段",
            "content": "这是该时间块的总结。",
            "start_time": 60,
            "end_time": 150,
        }
    ]


def test_seconds_from_timestamp_supports_hours():
    assert seconds_from_timestamp("01:02:03") == 3723


def test_timeline_sections_have_ranges_rejects_zero_ranges():
    assert not timeline_sections_have_ranges([{"start_time": 0, "end_time": 0}])
    assert timeline_sections_have_ranges([{"start_time": 0, "end_time": 12}])


def test_build_timeline_sections_from_segments_uses_hints_without_timestamps():
    sections = build_timeline_sections_from_segments(
        [
            {"start": 0, "end": 5, "text": "第一句"},
            {"start": 5, "end": 10, "text": "第二句"},
            {"start": 10, "end": 16, "text": "第三句"},
            {"start": 16, "end": 22, "text": "第四句"},
        ],
        hints=[
            {"title": "开场", "content": "介绍背景", "chunk_index": 0},
            {"title": "展开", "content": "说明观点", "chunk_index": 1},
        ],
    )

    assert sections == [
        {
            "title": "开场",
            "start_time": 0,
            "end_time": 10,
            "content": "介绍背景",
            "chunk_index": 0,
        },
        {
            "title": "展开",
            "start_time": 10,
            "end_time": 22,
            "content": "说明观点",
            "chunk_index": 1,
        },
    ]
