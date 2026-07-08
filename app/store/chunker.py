# app/store/chunker.py
import re
from typing import List, Dict, Any
from app.note.timeline import extract_timeline_sections, seconds_from_timestamp

def semantic_chunk(note_markdown: str, min_chunk_size: int = 100, overlap: int = 50) -> List[Dict[str, Any]]:
    """按 ## 标题分割，合并小块，添加重叠"""
    timeline_sections = extract_timeline_sections(note_markdown)
    if timeline_sections:
        return [
            {
                "title": section.get("title", f"片段 {index + 1}"),
                "content": section.get("content") or section.get("title", ""),
                "start_time": section.get("start_time", 0),
                "end_time": section.get("end_time", 0),
            }
            for index, section in enumerate(timeline_sections)
        ]

    # 按行分割，识别标题
    lines = note_markdown.split("\n")
    chunks = []
    current_chunk = {"title": "", "content": "", "start_time": 0, "end_time": 0}
    # 用于提取时间戳的函数
    time_pattern = re.compile(r"[（(［\[](\d{1,2}:\d{2}(?::\d{2})?)\s*(?:-|~|–|—|至|到)\s*(\d{1,2}:\d{2}(?::\d{2})?)[）)］\]]")

    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            # 新章节开始，保存上一个
            if current_chunk["content"]:
                chunks.append(current_chunk.copy())
            # 提取标题和时间
            title_text = line.lstrip("#").strip()
            time_match = time_pattern.search(title_text)
            if time_match:
                title = title_text[:time_match.start()].strip()
                start_str, end_str = time_match.groups()
                start = seconds_from_timestamp(start_str)
                end = seconds_from_timestamp(end_str)
            else:
                title = title_text
                start = end = 0
            current_chunk = {"title": title, "content": "", "start_time": start, "end_time": end}
        else:
            current_chunk["content"] += line + "\n"
    if current_chunk["content"]:
        chunks.append(current_chunk)

    # 合并小块
    merged = []
    buffer = ""
    for chunk in chunks:
        if len(buffer) + len(chunk["content"]) < min_chunk_size:
            buffer += chunk["content"] + "\n"
        else:
            if buffer:
                merged.append({"title": "合并块", "content": buffer, "start_time": 0, "end_time": 0})
            buffer = chunk["content"] + "\n"
    if buffer:
        merged.append({"title": "合并块", "content": buffer, "start_time": 0, "end_time": 0})

    # 添加重叠（跨块保留最后 overlap 字符）
    final_chunks = []
    for i, chunk in enumerate(merged):
        content = chunk["content"]
        if i > 0:
            # 从前一个块的末尾取 overlap 字符
            prev_content = final_chunks[-1]["content"]
            overlap_text = prev_content[-overlap:] if len(prev_content) >= overlap else prev_content
            content = overlap_text + "\n" + content
        final_chunks.append({
            "title": chunk["title"],
            "content": content,
            "start_time": chunk.get("start_time", 0),
            "end_time": chunk.get("end_time", 0),
        })
    return final_chunks
