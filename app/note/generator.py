# app/note/generator.py
import re
from typing import List, Dict, Any
from app.llm.client import get_llm_client
from app.core.logger import logger

class NoteGenerator:
    def __init__(self):
        self.llm = get_llm_client()

    async def generate(self, transcript_text: str, video_meta: Dict[str, Any]) -> Dict[str, Any]:
        """返回包含 markdown_content, summary, keywords, sections 的字典"""
        # 1. 构建 Prompt（使用 Prompt 工程文档中的模板）
        system_prompt = """你是一个专业的视频笔记整理助手。你的任务是将视频的语音转写文本转化为结构清晰、内容完整的 Markdown 笔记。

## 核心要求
1. 忠实原文：只基于转写文本中的内容
2. 结构化：识别视频自然语义分段，按章节整理
3. 时间标注：每个章节标注起止时间（格式 MM:SS - MM:SS）
4. 完整性：覆盖所有重要知识点
5. 客观性：保持中立语气

## 输出格式
# {视频标题}

## 摘要
用 2-4 句话概括核心内容。

## 关键词
- 关键词1
- 关键词2

## 内容整理
### 章节一：{标题}（MM:SS - MM:SS）
{内容整理}

## 核心观点总结
1. ...
2. ...

## 金句摘录
> 精彩语句
> -- 出处（MM:SS）"""

        user_prompt = f"""请根据以下视频信息，生成结构化笔记。

## 视频信息
- 标题：{video_meta.get('title', '未命名视频')}
- UP 主：{video_meta.get('uploader', '未知')}
- 时长：{video_meta.get('duration_seconds', 0)} 秒

## 转写文本
{transcript_text}

请按上述要求生成 Markdown 笔记。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 2. 调用 LLM（非流式）
        logger.info(f"开始生成笔记，视频: {video_meta.get('title')}")
        markdown_content = await self.llm.chat(messages, temperature=0.1)

        # 3. 解析 Markdown，提取摘要、关键词、章节列表
        parsed = self._parse_markdown(markdown_content)
        parsed["markdown_content"] = markdown_content
        return parsed

    def _parse_markdown(self, markdown: str) -> Dict[str, Any]:
        """从 Markdown 中提取摘要、关键词和章节（二级标题）"""
        # 简易解析（实际生产可考虑使用 markdown 库）
        lines = markdown.split("\n")
        summary = ""
        keywords = []
        sections = []
        current_section = None
        in_summary = False
        in_keywords = False

        for line in lines:
            line = line.strip()
            if line.startswith("## 摘要"):
                in_summary = True
                in_keywords = False
                continue
            elif line.startswith("## 关键词"):
                in_summary = False
                in_keywords = True
                continue
            elif line.startswith("## 内容整理"):
                in_summary = False
                in_keywords = False
                continue
            elif line.startswith("###"):
                # 章节标题，格式：### 章节名（MM:SS - MM:SS）
                if current_section:
                    sections.append(current_section)
                title_match = re.match(r"### (.+)（(\d+:\d+) - (\d+:\d+)）", line)
                if title_match:
                    title = title_match.group(1).strip()
                    start_str = title_match.group(2)
                    end_str = title_match.group(3)
                    # 将 MM:SS 转为秒数
                    def to_seconds(ts):
                        parts = ts.split(":")
                        if len(parts) == 2:
                            return int(parts[0])*60 + int(parts[1])
                        else:
                            return 0
                    start = to_seconds(start_str)
                    end = to_seconds(end_str)
                    current_section = {"title": title, "start_time": start, "end_time": end, "content": ""}
                else:
                    # 可能标题格式不标准，直接当作标题处理
                    current_section = {"title": line.replace("###", "").strip(), "start_time": 0, "end_time": 0, "content": ""}
            elif in_summary:
                if line and not line.startswith("##"):
                    summary += line + "\n"
            elif in_keywords:
                if line.startswith("- "):
                    keywords.append(line[2:].strip())
            elif current_section is not None:
                # 累积章节内容（跳过空行）
                if line:
                    current_section["content"] += line + "\n"

        if current_section:
            sections.append(current_section)

        return {
            "summary": summary.strip(),
            "keywords": keywords,
            "sections": sections,
        }