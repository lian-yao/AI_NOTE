from __future__ import annotations

import copy
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIXTURE_BVID = "BV1aeLqzUE6L"
FIXTURE_SOURCE_URL = (
    "https://www.bilibili.com/video/BV1aeLqzUE6L/"
    "?spm_id_from=333.337.search-card.all.click&vd_source=468f1a9e75e01aac8f044869f34d0717"
)
TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "tests" / "test_data"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug_from_url(url: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if match:
        return match.group(1)

    if url.startswith("local://"):
        return url.replace("local://", "local-")

    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", url).strip("-").lower()
    return cleaned[:18] or uuid.uuid4().hex[:10]


def seconds_from_timestamp(value: str) -> int:
    parts = [int(part) for part in value.strip().split(":")]
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


def parse_transcript_markdown(markdown: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    line_re = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\]\s*(.+)$")
    for line in markdown.splitlines():
        match = line_re.match(line.strip())
        if not match:
            continue
        segments.append(
            {
                "start": seconds_from_timestamp(match.group(1)),
                "end": seconds_from_timestamp(match.group(2)),
                "text": match.group(3).strip(),
            }
        )
    return segments


def parse_timeline_sections(markdown: str, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    line_re = re.compile(
        r"^- \[(\d{2}:\d{2}(?::\d{2})?)\s*-\s*(\d{2}:\d{2}(?::\d{2})?)\]\s*"
        r"\*\*(.+?)\*\*:\s*(.+)$"
    )
    for line in markdown.splitlines():
        match = line_re.match(line.strip())
        if not match:
            continue
        sections.append(
            {
                "title": match.group(3).strip(),
                "start_time": seconds_from_timestamp(match.group(1)),
                "end_time": seconds_from_timestamp(match.group(2)),
                "content": match.group(4).strip(),
                "chunk_index": len(sections),
            }
        )

    if sections:
        return sections

    for chapter in chapters:
        sections.append(
            {
                "title": str(chapter.get("title") or f"Chapter {len(sections) + 1}"),
                "start_time": int(chapter.get("start_time") or 0),
                "end_time": int(chapter.get("end_time") or 0),
                "content": str(chapter.get("title") or ""),
                "chunk_index": len(sections),
            }
        )
    return sections


def compact_media_format(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "format_id": item.get("format_id"),
        "format": item.get("format"),
        "url": item.get("url"),
        "ext": item.get("ext"),
        "width": item.get("width"),
        "height": item.get("height"),
        "fps": item.get("fps"),
        "resolution": item.get("resolution"),
        "vcodec": item.get("vcodec"),
        "acodec": item.get("acodec"),
        "filesize_approx": item.get("filesize_approx"),
    }


def upload_date_from_metadata(metadata: dict[str, Any]) -> str | None:
    value = str(metadata.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    timestamp = metadata.get("timestamp")
    if isinstance(timestamp, int):
        return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
    return None


def archive_id_from_metadata(metadata: dict[str, Any]) -> int | None:
    for item in metadata.get("_old_archive_ids") or []:
        match = re.search(r"(\d+)", str(item))
        if match:
            return int(match.group(1))
    return None


def default_segments(title: str) -> list[dict[str, Any]]:
    lines = [
        f"Welcome to this mock walkthrough for {title}.",
        "The downloader stage extracts media metadata and prepares an audio file.",
        "The transcriber stage turns the audio into timestamped text segments.",
        "The note generator groups the transcript into topics, actions, and references.",
        "The QA index is built from note sections so the chat panel can answer questions.",
        "This data is deterministic enough for frontend tests and still feels like a real flow.",
    ]
    return [
        {
            "start": index * 18,
            "end": index * 18 + 14,
            "text": text,
        }
        for index, text in enumerate(lines)
    ]


def build_markdown(title: str, style: str = "minimal", extras: str | None = None) -> str:
    prompt_line = f"\n\n> Extra prompt: {extras.strip()}" if extras else ""
    return f"""# {title}

## Summary

This is a mock note generated by the standalone backend service. It exercises the same frontend path as a real video task: parse, process, poll task status, render markdown, inspect transcript, and ask questions.

## Key Points

- The mock service exposes the `/api/v1` contract used by the React frontend.
- Task status advances over time from pending to completed.
- The final result contains markdown, transcript segments, and audio metadata.
- Settings, provider, model, transcriber, proxy, upload, and QA endpoints are all backed by in-memory data.

## Suggested Follow-up

Use this flow to test empty states, loading states, completed notes, retries, settings screens, and the chat panel without running external video, model, or vector services.

## Generation Profile

- Style: `{style}`
- Provider: mock-provider
- Model: mock-llm{prompt_line}
"""


class MockBackendStore:
    def __init__(self) -> None:
        now = utc_now()
        self.start_monotonic = time.monotonic()
        self.system_config: dict[str, Any] = {
            "llm_provider": "mock-provider",
            "llm_model": "mock-llm",
            "transcriber_mode": "fast-whisper",
            "whisper_model_size": "base",
            "whisper_device": "cpu",
            "embedding_model": "mock-embedding",
            "retrieval_top_k": 5,
            "data_dir": "./mock_backend/.data",
            "video_retention": "processed",
        }
        self.storage_config: dict[str, Any] = {
            "dataRootPath": "./mock_backend/.data",
            "cacheRootPath": "./mock_backend/.data/cache",
            "cacheDirectories": {
                "downloads": "./mock_backend/.data/cache/downloads",
                "transcripts": "./mock_backend/.data/cache/transcripts",
                "covers": "./mock_backend/.data/cache/covers",
                "temp": "./mock_backend/.data/cache/temp",
            },
            "lastCacheClearedAt": None,
        }
        self.storage_cache_usage: dict[str, int] = {
            "downloads": 12 * 1024 * 1024,
            "transcripts": 3 * 1024 * 1024,
            "covers": 2 * 1024 * 1024,
            "temp": 512 * 1024,
        }
        self.proxy_config: dict[str, Any] = {
            "enabled": False,
            "url": "",
            "effective": "",
        }
        self.cookies: dict[str, str] = {
            "bilibili": "SESSDATA=mock_cookie; bili_jct=mock_csrf",
        }
        self.transcriber_config: dict[str, Any] = {
            "transcriber_type": "fast-whisper",
            "whisper_model_size": "base",
            "whisper_device": "auto",
            "available_types": [
                {"value": "fast-whisper", "label": "Fast Whisper"},
            ],
            "whisper_model_sizes": ["tiny", "base", "small", "medium", "large-v3", "turbo"],
            "whisper_builtin_models": {
                "tiny": "Systran/faster-whisper-tiny",
                "base": "Systran/faster-whisper-base",
                "small": "Systran/faster-whisper-small",
                "medium": "Systran/faster-whisper-medium",
                "large-v3": "Systran/faster-whisper-large-v3",
                "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
            },
            "whisper_custom_models": {},
            "mlx_whisper_available": False,
        }
        self.downloaded_whisper_models: set[str] = {"base"}
        self.providers: list[dict[str, Any]] = [
            {
                "id": "mock-provider",
                "name": "Mock Provider",
                "logo": "custom",
                "type": "mock",
                "base_url": "mock://local",
                "enabled": True,
                "has_api_key": False,
                "api_key": "",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "openai-compatible",
                "name": "OpenAI Compatible Demo",
                "logo": "openai",
                "type": "openai-compatible",
                "base_url": "https://api.example.test/v1",
                "enabled": True,
                "has_api_key": True,
                "api_key": "******",
                "created_at": now,
                "updated_at": now,
            },
        ]
        self.models: list[dict[str, Any]] = [
            {
                "id": 10001,
                "provider_id": "mock-provider",
                "model_name": "mock-llm",
                "enabled": True,
                "created_at": now,
            },
            {
                "id": 10002,
                "provider_id": "mock-provider",
                "model_name": "mock-vision-llm",
                "enabled": True,
                "created_at": now,
            },
            {
                "id": 10003,
                "provider_id": "openai-compatible",
                "model_name": "gpt-4o-mini-demo",
                "enabled": True,
                "created_at": now,
            },
        ]
        self.remote_models: dict[str, list[dict[str, Any]]] = {
            "mock-provider": [
                {
                    "id": "mock-llm",
                    "object": "model",
                    "display_name": "Mock LLM",
                    "owned_by": "mock",
                },
                {
                    "id": "mock-vision-llm",
                    "object": "model",
                    "display_name": "Mock Vision LLM",
                    "owned_by": "mock",
                },
            ],
            "openai-compatible": [
                {
                    "id": "gpt-4o-mini-demo",
                    "object": "model",
                    "display_name": "GPT-4o mini Demo",
                    "owned_by": "demo",
                },
                {
                    "id": "qwen-plus-demo",
                    "object": "model",
                    "display_name": "Qwen Plus Demo",
                    "owned_by": "demo",
                },
            ],
        }
        self.uploads: dict[str, dict[str, Any]] = {}
        self.videos: dict[str, dict[str, Any]] = {}
        self.notes: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.next_model_id = 20000
        self.next_note_id = 1
        self.next_video_pk = 1
        self.fixture_data = self._load_fixture_data()
        if env_flag("AI_NOTE_MOCK_SEED_DEMO", default=True):
            self._seed_completed_video()

    def clone(self, value: Any) -> Any:
        return copy.deepcopy(value)

    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self.start_monotonic)

    def _load_fixture_note(self) -> str | None:
        if not TEST_DATA_DIR.exists():
            return None
        for path in TEST_DATA_DIR.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if FIXTURE_BVID in text:
                return text
        return None

    def _load_fixture_data(self) -> dict[str, Any] | None:
        cache_dir = TEST_DATA_DIR / ".cache"
        metadata_path = cache_dir / f"{FIXTURE_BVID}.metadata.json"
        transcript_path = cache_dir / f"{FIXTURE_BVID}.transcript.whisper-large-v3-turbo.md"

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        note_markdown = self._load_fixture_note()
        if not note_markdown:
            note_markdown = build_markdown(str(metadata.get("title") or FIXTURE_BVID))

        try:
            transcript_markdown = transcript_path.read_text(encoding="utf-8")
        except OSError:
            transcript_markdown = ""

        segments = parse_transcript_markdown(transcript_markdown)
        chapters = metadata.get("chapters") if isinstance(metadata.get("chapters"), list) else []
        sections = parse_timeline_sections(note_markdown, chapters)
        title = str(metadata.get("title") or metadata.get("fulltitle") or FIXTURE_BVID)
        thumbnail = str(
            metadata.get("thumbnail")
            or ((metadata.get("thumbnails") or [{}])[0].get("url") if metadata.get("thumbnails") else "")
            or f"/static/mock-cover/b_{FIXTURE_BVID}.svg"
        )
        video_stream = None
        audio_stream = None
        requested_formats = metadata.get("requested_formats") or []
        formats = metadata.get("formats") or []
        for item in [*requested_formats, *formats]:
            if not isinstance(item, dict):
                continue
            if video_stream is None and item.get("vcodec") and item.get("vcodec") != "none":
                video_stream = item
            if audio_stream is None and item.get("acodec") and item.get("acodec") != "none":
                audio_stream = item
            if video_stream and audio_stream:
                break

        parsed = {
            "video_id": f"b_{FIXTURE_BVID}",
            "url": metadata.get("webpage_url") or FIXTURE_SOURCE_URL,
            "source_url": metadata.get("webpage_url") or FIXTURE_SOURCE_URL,
            "title": title,
            "uploader": metadata.get("uploader") or "Bilibili",
            "uploader_uid": str(metadata.get("uploader_id") or ""),
            "duration_seconds": int(round(float(metadata.get("duration") or 0))),
            "cover_url": thumbnail,
            "bvid": FIXTURE_BVID,
            "avid": archive_id_from_metadata(metadata),
            "description": metadata.get("description") or "",
            "is_playlist": False,
            "playlist_title": None,
            "player_url": f"https://www.bilibili.com/video/{FIXTURE_BVID}/",
            "embed_url": f"https://player.bilibili.com/player.html?bvid={FIXTURE_BVID}&autoplay=0",
            "upload_date": upload_date_from_metadata(metadata),
            "view_count": metadata.get("view_count"),
            "like_count": metadata.get("like_count"),
            "comment_count": metadata.get("comment_count"),
            "tags": metadata.get("tags") or [],
            "chapters": chapters,
            "video_stream": compact_media_format(video_stream),
            "audio_stream": compact_media_format(audio_stream),
        }
        raw_info = {
            "uploader": parsed["uploader"],
            "uploader_uid": parsed["uploader_uid"],
            "bvid": FIXTURE_BVID,
            "avid": parsed["avid"],
            "description": parsed["description"],
            "source_url": parsed["url"],
            "player_url": parsed["player_url"],
            "embed_url": parsed["embed_url"],
            "thumbnail": thumbnail,
            "duration_string": metadata.get("duration_string"),
            "upload_date": parsed["upload_date"],
            "view_count": parsed["view_count"],
            "like_count": parsed["like_count"],
            "comment_count": parsed["comment_count"],
            "tags": parsed["tags"],
            "chapters": chapters,
            "video_stream": parsed["video_stream"],
            "audio_stream": parsed["audio_stream"],
            "formats": [compact_media_format(item) for item in formats if isinstance(item, dict)],
        }
        return {
            "parsed": parsed,
            "markdown": note_markdown,
            "transcript_markdown": transcript_markdown,
            "segments": segments,
            "sections": sections,
            "raw_info": raw_info,
            "file_size": metadata.get("filesize_approx") or 27_399_380,
            "metadata": metadata,
        }

    def _seed_completed_video(self) -> None:
        parsed = self.parse_video_url(FIXTURE_SOURCE_URL)
        task_id = "task-seeded-demo"
        self._upsert_processed_video(parsed, task_id, "minimal", None, created_offset=180)
        task = self.tasks[task_id]
        task["created_monotonic"] = time.monotonic() - 999
        task["status_override"] = "completed"

    def parse_video_url(self, url: str) -> dict[str, Any]:
        slug = slug_from_url(url)
        if slug == FIXTURE_BVID and self.fixture_data:
            parsed = self.clone(self.fixture_data["parsed"])
            parsed["url"] = url or parsed["url"]
            parsed["source_url"] = parsed["url"]
            return parsed

        is_local = url.startswith("local://")
        title_prefix = "Local upload" if is_local else "Bilibili demo"
        title = f"{title_prefix} {slug}"
        video_id = f"local_{slug}" if is_local else f"b_{slug}"
        return {
            "video_id": video_id,
            "url": url,
            "title": title,
            "uploader": "Mock Studio",
            "uploader_uid": "10086",
            "duration_seconds": 128 + (len(slug) % 6) * 45,
            "cover_url": f"/static/mock-cover/{video_id}.svg",
            "bvid": slug if slug.startswith("BV") else None,
            "avid": abs(hash(slug)) % 100000000,
            "description": "Generated by the standalone mock backend service.",
            "is_playlist": False,
            "playlist_title": None,
            "source_url": url,
            "player_url": f"https://www.bilibili.com/video/{slug}/" if slug.startswith("BV") else None,
            "embed_url": (
                f"https://player.bilibili.com/player.html?bvid={slug}&autoplay=0"
                if slug.startswith("BV")
                else None
            ),
        }

    def _upsert_processed_video(
        self,
        parsed: dict[str, Any],
        task_id: str,
        style: str,
        extras: str | None,
        created_offset: int = 0,
    ) -> dict[str, Any]:
        now = utc_now()
        video_id = parsed["video_id"]
        created_at = now
        fixture = self.fixture_data if parsed.get("bvid") == FIXTURE_BVID else None
        markdown = fixture["markdown"] if fixture else build_markdown(parsed["title"], style, extras)
        segments = fixture["segments"] if fixture else default_segments(parsed["title"])
        sections = (
            self.clone(fixture["sections"])
            if fixture
            else [
                {
                    "title": "Summary",
                    "start_time": 0,
                    "end_time": 60,
                    "content": "Mock summary and workflow overview.",
                    "chunk_index": 0,
                },
                {
                    "title": "Implementation Flow",
                    "start_time": 60,
                    "end_time": 150,
                    "content": "Parse, process, poll task state, render note, and ask questions.",
                    "chunk_index": 1,
                },
            ]
        )
        raw_info = (
            self.clone(fixture["raw_info"])
            if fixture
            else {
                "uploader": parsed["uploader"],
                "uploader_uid": parsed["uploader_uid"],
                "bvid": parsed.get("bvid"),
                "avid": parsed.get("avid"),
                "description": parsed.get("description"),
            }
        )
        transcript = {
            "full_text": " ".join(segment["text"] for segment in segments),
            "language": "zh-CN" if fixture else "en-US",
            "raw": fixture["transcript_markdown"] if fixture else None,
            "segments": segments,
        }
        audio_meta = {
            "cover_url": parsed["cover_url"],
            "duration": parsed["duration_seconds"],
            "file_path": f"./mock_backend/.data/audio/{video_id}.m4a",
            "platform": "local" if parsed["url"].startswith("local://") else "bilibili",
            "raw_info": raw_info,
            "title": parsed["title"],
            "video_id": video_id,
            "source_url": parsed["url"],
            "player_url": parsed.get("player_url"),
            "embed_url": parsed.get("embed_url"),
            "chapters": parsed.get("chapters") or sections,
        }
        result = {
            "markdown": markdown,
            "transcript": transcript,
            "audio_meta": audio_meta,
        }
        video = {
            "id": self.videos.get(video_id, {}).get("id", self.next_video_pk),
            "video_id": video_id,
            "url": parsed["url"],
            "title": parsed["title"],
            "uploader": parsed["uploader"],
            "uploader_uid": parsed["uploader_uid"],
            "description": parsed["description"],
            "duration_seconds": parsed["duration_seconds"],
            "cover_url": parsed["cover_url"],
            "bvid": parsed.get("bvid"),
            "avid": parsed.get("avid"),
            "status": "pending",
            "has_note": False,
            "file_size": int(
                fixture.get("file_size")
                if fixture
                else 24_000_000 + parsed["duration_seconds"] * 4096
            ),
            "audio_path": audio_meta["file_path"],
            "video_path": f"./mock_backend/.data/videos/{video_id}.mp4",
            "source_url": parsed["url"],
            "player_url": parsed.get("player_url"),
            "embed_url": parsed.get("embed_url"),
            "upload_date": parsed.get("upload_date"),
            "view_count": parsed.get("view_count"),
            "like_count": parsed.get("like_count"),
            "comment_count": parsed.get("comment_count"),
            "tags": parsed.get("tags") or [],
            "chapters": parsed.get("chapters") or sections,
            "video_stream": parsed.get("video_stream"),
            "audio_stream": parsed.get("audio_stream"),
            "processed_at": None,
            "created_at": created_at,
            "updated_at": now,
        }
        if video_id not in self.videos:
            self.next_video_pk += 1
        note = {
            "id": self.notes.get(video_id, {}).get("id", self.next_note_id),
            "video_id": video_id,
            "video_title": parsed["title"],
            "file_path": f"./mock_backend/.data/notes/{video_id}.md",
            "summary": markdown,
            "keywords": parsed.get("tags") or ["mock", "frontend-test", "video-note"],
            "sections": sections,
            "total_chunks": len(segments),
            "section_count": len(sections),
            "char_count": len(markdown),
            "model_used": "mock-llm",
            "created_at": created_at,
            "updated_at": now,
            "raw_markdown": markdown,
        }
        if video_id not in self.notes:
            self.next_note_id += 1
        task = {
            "task_id": task_id,
            "video_id": video_id,
            "type": "generate",
            "status": "pending",
            "progress": 0,
            "error_message": None,
            "retry_count": self.tasks.get(task_id, {}).get("retry_count", 0),
            "started_at": None,
            "completed_at": None,
            "created_at": created_at,
            "created_monotonic": time.monotonic() - created_offset,
            "result": result,
            "logs": [],
        }
        self.videos[video_id] = video
        self.notes[video_id] = note
        self.tasks[task_id] = task
        return task

    def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        url = str(body.get("url") or body.get("video_url") or body.get("source_url") or "").strip()
        if not url:
            url = "https://www.bilibili.com/video/BV1MockGenerated"
        parsed = self.parse_video_url(url)
        task_id = str(body.get("task_id") or f"mock-task-{uuid.uuid4().hex[:12]}")
        style = str(body.get("style") or "minimal")
        extras = body.get("extras")
        task = self._upsert_processed_video(parsed, task_id, style, extras)
        return {
            "video_id": parsed["video_id"],
            "task_id": task["task_id"],
            "status": "pending",
        }

    def task_stage(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status_override") == "completed":
            return {
                "status": "completed",
                "progress": 100,
                "stage": "completed",
                "message": "Mock task completed.",
            }

        elapsed = time.monotonic() - float(task.get("created_monotonic", time.monotonic()))
        stages = [
            (0.0, "pending", 5, "queued", "Task is queued."),
            (0.8, "downloading", 24, "download", "Downloading mock media."),
            (2.2, "transcribing", 52, "transcribe", "Transcribing mock audio."),
            (4.0, "generating", 78, "generate", "Generating structured note."),
            (5.8, "storing", 92, "store", "Saving mock note and index."),
            (7.0, "completed", 100, "completed", "Mock task completed."),
        ]
        current = stages[0]
        for stage in stages:
            if elapsed >= stage[0]:
                current = stage
        status, progress, stage_name, message = current[1], current[2], current[3], current[4]
        return {
            "status": status,
            "progress": progress,
            "stage": stage_name,
            "message": message,
        }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        if not task:
            return None
        stage = self.task_stage(task)
        now = utc_now()
        task["status"] = stage["status"]
        task["progress"] = stage["progress"]
        if stage["status"] == "pending":
            task["started_at"] = None
        else:
            task["started_at"] = task["started_at"] or task["created_at"]
        if stage["status"] == "completed":
            task["completed_at"] = task["completed_at"] or now
            video = self.videos.get(task["video_id"])
            if video:
                video["status"] = "completed"
                video["has_note"] = True
                video["processed_at"] = task["completed_at"]
                video["updated_at"] = now
        else:
            video = self.videos.get(task["video_id"])
            if video:
                video["status"] = stage["status"]
                video["updated_at"] = now
        return self.clone(task)

    def list_task_logs(self, task_id: str) -> list[dict[str, Any]]:
        task = self.tasks.get(task_id)
        if not task:
            return []
        stage = self.task_stage(task)
        base = [
            ("INFO", "Task accepted", {"task_id": task_id}),
            ("INFO", "Mock media metadata parsed", {"video_id": task["video_id"]}),
        ]
        if stage["progress"] >= 24:
            base.append(("INFO", "Mock download completed", {"progress": 24}))
        if stage["progress"] >= 52:
            segment_count = len(task.get("result", {}).get("transcript", {}).get("segments", []))
            base.append(("INFO", "Mock transcript generated", {"segments": segment_count}))
        if stage["progress"] >= 78:
            base.append(("INFO", "Mock note generated", {"model": "mock-llm"}))
        if stage["progress"] >= 100:
            base.append(("INFO", "Task completed", {"progress": 100}))
        created_at = task["created_at"]
        return [
            {
                "id": index + 1,
                "task_id": task_id,
                "level": level,
                "message": message,
                "detail": str(detail),
                "created_at": created_at,
            }
            for index, (level, message, detail) in enumerate(base)
        ]

    def retry_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        if not task:
            return None
        task["created_monotonic"] = time.monotonic()
        task["created_at"] = utc_now()
        task["started_at"] = None
        task["completed_at"] = None
        task["status"] = "pending"
        task["progress"] = 0
        task["retry_count"] = int(task.get("retry_count") or 0) + 1
        task.pop("status_override", None)
        return {
            "task_id": task_id,
            "status": "pending",
            "retry_count": task["retry_count"],
        }

    def delete_video(self, video_id: str) -> dict[str, Any]:
        video = self.videos.pop(video_id, None)
        note = self.notes.pop(video_id, None)
        removed_tasks = [
            task_id for task_id, task in self.tasks.items() if task.get("video_id") == video_id
        ]
        for task_id in removed_tasks:
            self.tasks.pop(task_id, None)
        return {
            "deleted_video": bool(video),
            "deleted_notes": bool(note),
            "deleted_chunks": int(note.get("total_chunks", 0)) if note else 0,
            "deleted_vectors": int(note.get("total_chunks", 0)) if note else 0,
            "freed_space_bytes": int(video.get("file_size", 0)) if video else 0,
        }

    def qa_answer(self, query: str, video_id: str | None = None) -> dict[str, Any]:
        note = self.notes.get(video_id or "") if video_id else next(iter(self.notes.values()), None)
        if not note and self.notes:
            note = next(iter(self.notes.values()))
        title = note["video_title"] if note else "mock knowledge base"
        sections = note.get("sections", []) if note else []
        query_lower = query.lower()
        matched = [
            section
            for section in sections
            if str(section.get("title", "")).lower() in query_lower
            or any(word and word in str(section.get("content", "")).lower() for word in query_lower.split())
        ]
        selected = (matched or sections)[:3]
        if selected:
            first = selected[0]
            answer = (
                f"Mock answer for: {query}\n\n"
                f"这条回答基于 `{title}` 的「{first.get('title')}」片段，"
                f"时间点约为 {timestamp_from_seconds(first.get('start_time'))}。"
                "Mock 后端会返回真实测试视频的章节和字幕时间戳，方便前端测试问答引用跳转。"
            )
        else:
            answer = (
                f"Mock answer for: {query}\n\n"
                f"The referenced content comes from `{title}`. "
                "This response is generated locally so the chat UI can be tested without an LLM API."
            )
        references = [
            {
                "chunk_id": f"{note['video_id']}_{index}" if note else f"mock_{index}",
                "video_id": note["video_id"] if note else "mock",
                "video_title": title,
                "section_title": section.get("title") or "Summary",
                "content": section.get("content") or "Mock source content.",
                "start_time": section.get("start_time"),
                "end_time": section.get("end_time"),
                "relevance_score": round(0.93 - index * 0.06, 2),
            }
            for index, section in enumerate(selected or [{"content": "Mock source content."}])
        ]
        return {
            "answer": answer,
            "references": references,
            "token_usage": {
                "prompt_tokens": 128,
                "completion_tokens": 96,
                "total_tokens": 224,
            },
        }


store = MockBackendStore()
