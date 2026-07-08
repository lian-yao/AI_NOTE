"""Timeline helpers for timestamped video notes."""

from __future__ import annotations

import re
from typing import Any


TIMESTAMP_RE = r"\d{1,2}:\d{2}(?::\d{2})?"
RANGE_SEP_RE = r"(?:-|~|–|—|至|到)"
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=['\"]([^'\"]+)['\"][^>]*>", re.I)


def seconds_from_timestamp(value: str | int | float | None) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if not value:
        return 0

    parts = [int(part) for part in str(value).strip().split(":") if part.isdigit()]
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    return parts[0] if parts else 0


def timestamp_from_seconds(value: int | float | None) -> str:
    seconds = max(0, int(value or 0))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def clean_section_title(value: str) -> str:
    cleaned = re.sub(
        rf"[（(［\[]\s*{TIMESTAMP_RE}\s*{RANGE_SEP_RE}\s*{TIMESTAMP_RE}\s*[）)］\]]",
        "",
        value,
    )
    cleaned = re.sub(r"^章节\s*[一二三四五六七八九十百\d]+\s*[:：-]\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(
        r"^第[一二三四五六七八九十百\d]+(?:章节|部分|章|节|部|分)\s*[:：-]?\s*",
        "",
        cleaned,
    )
    return cleaned.strip()


def extract_first_image_url(value: str) -> str:
    markdown_match = MARKDOWN_IMAGE_RE.search(value)
    if markdown_match:
        return markdown_match.group(1).strip()

    html_match = HTML_IMAGE_RE.search(value)
    if html_match:
        return html_match.group(1).strip()

    return ""


def strip_images(value: str) -> str:
    return HTML_IMAGE_RE.sub("", MARKDOWN_IMAGE_RE.sub("", value)).strip()


def timeline_sections_have_ranges(sections: list[dict[str, Any]]) -> bool:
    """Return true when at least one section carries a usable time range."""

    for section in sections:
        start_time = seconds_from_timestamp(section.get("start_time"))
        end_time = seconds_from_timestamp(section.get("end_time"))
        if end_time > start_time:
            return True
    return False


def build_timeline_sections_from_segments(
    segments: list[dict[str, Any]],
    hints: list[dict[str, Any]] | None = None,
    group_size: int = 8,
) -> list[dict[str, Any]]:
    """Build stable timeline sections from transcript segments.

    LLM-produced timestamps are useful when they are valid, but deep reading needs
    deterministic ranges. This helper uses the transcript itself as the source of truth.
    """

    clean_segments: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start_time = seconds_from_timestamp(segment.get("start"))
        end_time = seconds_from_timestamp(segment.get("end"))
        clean_segments.append(
            {
                "start": start_time,
                "end": max(end_time, start_time),
                "text": text,
            }
        )

    clean_segments.sort(key=lambda item: item["start"])
    if not clean_segments:
        return []

    hints = hints or []
    desired_count = len(hints) or max(1, (len(clean_segments) + max(1, group_size) - 1) // max(1, group_size))
    group_count = min(len(clean_segments), max(1, desired_count))
    sections: list[dict[str, Any]] = []

    for index in range(group_count):
        start_index = (index * len(clean_segments)) // group_count
        end_index = max(
            start_index,
            ((index + 1) * len(clean_segments)) // group_count - 1,
        )
        group = clean_segments[start_index : end_index + 1]
        hint = hints[index] if index < len(hints) else {}
        text = " ".join(item["text"] for item in group)
        title = str(hint.get("title") or "").strip() or text[:28] or f"片段 {index + 1}"
        content = strip_images(str(hint.get("content") or text))
        section = {
            "title": title,
            "start_time": group[0]["start"],
            "end_time": max(group[-1]["end"], group[0]["start"]),
            "content": content,
            "chunk_index": hint.get("chunk_index", index),
        }
        if hint.get("screenshot_url"):
            section["screenshot_url"] = hint["screenshot_url"]
        sections.append(section)

    return sections


def extract_timeline_sections(markdown: str) -> list[dict[str, Any]]:
    """Extract AI summary blocks that carry real timestamp ranges."""

    sections: list[dict[str, Any]] = []
    heading_re = re.compile(
        rf"^#{{2,6}}\s+(.+?)[（(［\[]\s*({TIMESTAMP_RE})\s*{RANGE_SEP_RE}\s*"
        rf"({TIMESTAMP_RE})\s*[）)］\]]\s*$"
    )
    bullet_re = re.compile(
        rf"^\s*[-*]\s+\[\s*({TIMESTAMP_RE})\s*{RANGE_SEP_RE}\s*({TIMESTAMP_RE})\s*\]\s*"
        r"(?:(?:\*\*)?([^*:：]+)(?:\*\*)?\s*[:：-])?\s*(.*)$"
    )
    current: dict[str, Any] | None = None

    def push_current() -> None:
        nonlocal current
        if not current:
            return
        content = str(current.get("content") or "").strip()
        screenshot_url = extract_first_image_url(content)
        current["content"] = strip_images(content)
        if screenshot_url:
            current["screenshot_url"] = screenshot_url
        current["chunk_index"] = len(sections)
        if not current.get("title"):
            current["title"] = f"片段 {len(sections) + 1}"
        sections.append(current)
        current = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        heading_match = heading_re.match(line)
        if heading_match:
            push_current()
            start_time = seconds_from_timestamp(heading_match.group(2))
            end_time = seconds_from_timestamp(heading_match.group(3))
            current = {
                "title": clean_section_title(heading_match.group(1)) or f"片段 {len(sections) + 1}",
                "start_time": start_time,
                "end_time": max(end_time, start_time),
                "content": "",
            }
            continue

        bullet_match = bullet_re.match(line)
        if bullet_match:
            push_current()
            start_time = seconds_from_timestamp(bullet_match.group(1))
            end_time = seconds_from_timestamp(bullet_match.group(2))
            content = (bullet_match.group(4) or "").strip()
            section = {
                "title": clean_section_title(bullet_match.group(3) or "")
                or f"片段 {len(sections) + 1}",
                "start_time": start_time,
                "end_time": max(end_time, start_time),
                "content": strip_images(content),
                "chunk_index": len(sections),
            }
            screenshot_url = extract_first_image_url(content)
            if screenshot_url:
                section["screenshot_url"] = screenshot_url
            sections.append(section)
            continue

        if current is not None and line and not line.startswith("#"):
            current["content"] += raw_line.strip() + "\n"

    push_current()
    return sections
