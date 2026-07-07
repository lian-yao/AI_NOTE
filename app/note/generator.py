# app/note/generator.py
import re
from typing import List, Dict, Any
from app.llm.client import get_llm_client
from app.core.logger import logger

class NoteGenerator:
    """笔记生成器，将转录文本转化为结构化 Markdown 笔记。"""

    # ── 笔记风格 → 系统指令映射 ──
    _STYLE_INSTRUCTIONS: dict[str, str] = {
        "minimal": (
            "## 风格要求：精简\n"
            "- 只保留最核心的要点，每条控制在 1-2 句话\n"
            "- 省略冗余描述和背景铺垫，直击重点\n"
            "- 全文控制在 500 字以内，适合快速浏览"
        ),
        "detailed": (
            "## 风格要求：详细\n"
            "- 完整记录每个知识点，不遗漏细节\n"
            "- 每个章节附上详细的解释说明和上下文\n"
            "- 适当引用原视频中的例子和数据"
        ),
        "tutorial": (
            "## 风格要求：教程\n"
            "- 以教学视角组织内容，步骤清晰\n"
            "- 每个操作步骤标记序号（1. 2. 3. …）\n"
            "- 包含注意事项、常见错误和最佳实践提示"
        ),
        "academic": (
            "## 风格要求：学术\n"
            "- 使用学术写作风格，语言严谨\n"
            "- 梳理论点-论据结构，标注引用来源\n"
            "- 末尾添加「批判性思考」小节，指出局限和待商榷点"
        ),
        "xiaohongshu": (
            "## 风格要求：小红书\n"
            "- 开头用 Emoji + 吸引眼球的标题钩子\n"
            "- 正文分点列出，每段短小精悍（≤ 3 行）\n"
            "- 适当穿插 Emoji，语调亲切、口语化\n"
            "- 末尾加上话题标签 # 和总结推荐语"
        ),
        "life_journal": (
            "## 风格要求：生活向\n"
            "- 以叙事口吻重述视频内容，像讲故事\n"
            "- 突出个人感受、场景描写和情绪变化\n"
            "- 适合 vlog / 生活记录类视频"
        ),
        "task_oriented": (
            "## 风格要求：任务导向\n"
            "- 以「要做什么」和「怎么做」为主线\n"
            "- 每个章节以行动目标为标题\n"
            "- 末尾整理「行动清单」checklist"
        ),
        "business": (
            "## 风格要求：商业风格\n"
            "- 关注商业模式、市场分析和竞争格局\n"
            "- 提炼关键数据和逻辑链条\n"
            "- 末尾给出「商业启示」小结"
        ),
        "meeting_minutes": (
            "## 风格要求：会议纪要\n"
            "- 按议题/议程分段，每条标注讨论时间\n"
            "- 每个议题下分「结论」「待办」「责任人」\n"
            "- 末尾汇总所有待办事项"
        ),
    }

    def __init__(self, llm=None):
        """初始化笔记生成器。

        Args:
            llm: LLM 客户端实例。不传则用 get_llm_client() 自动创建。
        """
        self.llm = llm or get_llm_client()

    async def generate(
        self,
        transcript_text: str,
        video_meta: Dict[str, Any],
        style: str = "minimal",
        extras: str | None = None,
    ) -> Dict[str, Any]:
        """生成结构化 Markdown 笔记。

        Args:
            transcript_text: 语音转写全文
            video_meta: 视频元信息（标题、UP 主、时长等）
            style: 笔记风格，参考 _STYLE_INSTRUCTIONS 的 key
            extras: 用户自定义附加提示词

        Returns:
            包含 markdown_content, summary, keywords, sections 的字典
        """
        # 1. 构建基础 system prompt
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

        # 2. 追加风格指令
        style_instruction = self._STYLE_INSTRUCTIONS.get(style)
        if style_instruction:
            system_prompt += f"\n\n{style_instruction}"

        # 3. 构建 user prompt
        user_prompt = f"""请根据以下视频信息，生成结构化笔记。

## 视频信息
- 标题：{video_meta.get('title', '未命名视频')}
- UP 主：{video_meta.get('uploader', '未知')}
- 时长：{video_meta.get('duration_seconds', 0)} 秒

## 转写文本
{transcript_text}

请按上述要求生成 Markdown 笔记。"""

        # 4. 用户自定义提示词（extras）附加到末尾
        if extras:
            user_prompt += f"\n\n## 附加要求\n{extras}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 5. 调用 LLM（非流式）
        logger.info(f"开始生成笔记，视频: {video_meta.get('title')}, 风格: {style}")
        markdown_content = await self.llm.chat(messages, temperature=0.1)

        # 6. 解析 Markdown，提取摘要、关键词、章节列表
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
