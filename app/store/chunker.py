# app/store/chunker.py
import re
from typing import List, Dict, Any

def semantic_chunk(note_markdown: str, min_chunk_size: int = 100, overlap: int = 50) -> List[Dict[str, Any]]:
    """按 ## 标题分割，合并小块，添加重叠"""
    # 按行分割，识别标题
    lines = note_markdown.split("\n")
    chunks = []
    current_chunk = {"title": "", "content": "", "start_time": 0, "end_time": 0}
    # 用于提取时间戳的函数
    time_pattern = re.compile(r"（(\d+:\d+) - (\d+:\d+)）")

    for line in lines:
        if line.startswith("## "):
            # 新章节开始，保存上一个
            if current_chunk["content"]:
                chunks.append(current_chunk.copy())
            # 提取标题和时间
            title_text = line[3:].strip()
            time_match = time_pattern.search(title_text)
            if time_match:
                title = title_text[:time_match.start()].strip()
                start_str, end_str = time_match.groups()
                def to_sec(ts):
                    parts = ts.split(":")
                    return int(parts[0])*60 + int(parts[1]) if len(parts)==2 else 0
                start = to_sec(start_str)
                end = to_sec(end_str)
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