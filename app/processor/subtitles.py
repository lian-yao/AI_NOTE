"""Subtitle-first transcript helpers for Bilibili videos."""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from app.core.logger import logger
from app.schemas.stage import StageResult


TRANSCRIPT_JSON_NAME = "transcription.json"
TRANSCRIPT_SRT_NAME = "transcription.srt"

_BILIBILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}
_BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_LANG_PRIORITY = (
    "zh-hans",
    "zh-cn",
    "zh-sg",
    "ai-zh",
    "zh",
    "zh-hant",
    "zh-tw",
)
_SUBTITLE_SOURCES = {"bilibili-api", "yt-dlp-subtitles"}

_WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def is_subtitle_transcript_source(source: str | None) -> bool:
    return (source or "").strip().lower() in _SUBTITLE_SOURCES


def load_cached_transcript(video_dir: str) -> StageResult | None:
    """Load an existing transcription.json as a StageResult."""
    json_path = Path(video_dir) / TRANSCRIPT_JSON_NAME
    if not json_path.is_file():
        return None

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"读取转写缓存失败，将重新获取字幕: {exc}")
        return None

    segments = _normalize_segments(data.get("segments") or [])
    if not segments:
        return None

    full_text = str(data.get("full_text") or _full_text(segments))
    language = str(data.get("language") or "zh-CN")
    source = str(data.get("source") or data.get("transcript_source") or "cached")

    srt_path = Path(video_dir) / TRANSCRIPT_SRT_NAME
    if not srt_path.is_file():
        try:
            srt_path.write_text(_to_srt(segments), encoding="utf-8")
        except OSError:
            pass

    return StageResult(
        success=True,
        artifacts={
            "transcript_json": str(json_path),
            "transcript_srt": str(srt_path),
        },
        metadata={
            "full_text": full_text,
            "language": language,
            "segment_count": len(segments),
            "duration_seconds": _duration_seconds(segments),
            "source": source,
            "cached": True,
        },
    )


async def fetch_subtitle_transcript(url: str, video_dir: str) -> StageResult | None:
    """Fetch Bilibili subtitles, preferring the Bilibili API and falling back to yt-dlp."""
    try:
        api_segments = await _fetch_bilibili_api_segments(url)
        if api_segments:
            logger.info(f"字幕来源: bilibili-api segments={len(api_segments)}")
            return _write_transcript(video_dir, api_segments, "zh-CN", "bilibili-api")
    except Exception as exc:
        logger.warning(f"Bilibili API 字幕获取失败，尝试 yt-dlp 字幕: {exc}")

    try:
        ytdlp_segments = await _fetch_ytdlp_subtitle_segments(url)
        if ytdlp_segments:
            logger.info(f"字幕来源: yt-dlp-subtitles segments={len(ytdlp_segments)}")
            return _write_transcript(video_dir, ytdlp_segments, "zh-CN", "yt-dlp-subtitles")
    except Exception as exc:
        logger.warning(f"yt-dlp 字幕获取失败，将回退到本地转写/缓存: {exc}")

    return None


def _headers_with_cookie() -> dict[str, str]:
    headers = dict(_BILIBILI_HEADERS)
    try:
        from app.core.cookie_store import get_cookie

        cookie = get_cookie("bilibili") or ""
        if cookie:
            headers["Cookie"] = cookie
    except Exception:
        pass
    return headers


def _extract_bvid(value: str | None) -> str | None:
    if not value:
        return None
    match = _BVID_RE.search(value)
    return match.group(0) if match else None


def _extract_page(value: str | None) -> int:
    if not value:
        return 1
    try:
        parsed = urllib.parse.urlparse(value)
        page = urllib.parse.parse_qs(parsed.query).get("p", ["1"])[0]
        return max(1, int(page))
    except Exception:
        return 1


async def _fetch_bilibili_api_segments(url: str) -> list[dict[str, Any]]:
    bvid = _extract_bvid(url)
    if not bvid:
        return []

    headers = _headers_with_cookie()
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        view_resp = await client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
            headers=headers,
        )
        view_resp.raise_for_status()
        view_data = (view_resp.json() or {}).get("data") or {}
        aid = view_data.get("aid")
        pages = view_data.get("pages") or []
        if not aid or not pages:
            return []

        page_idx = min(max(_extract_page(url) - 1, 0), len(pages) - 1)
        cid = (pages[page_idx] or {}).get("cid")
        if not cid:
            return []

        params: dict[str, Any] = {"aid": aid, "cid": cid}
        mixin_key = await _get_wbi_mixin_key(client, headers)
        signed_params = _wbi_sign(params, mixin_key) if mixin_key else dict(params)

        player_data = await _request_player_data(client, signed_params, headers)
        subtitle_items = ((player_data.get("subtitle") or {}).get("subtitles") or [])
        if not subtitle_items:
            return []

        chosen = min(
            subtitle_items,
            key=lambda item: _language_rank(str(item.get("lan") or item.get("lan_doc") or "")),
        )
        subtitle_url = str(chosen.get("subtitle_url") or "")
        if subtitle_url.startswith("//"):
            subtitle_url = f"https:{subtitle_url}"
        if not subtitle_url:
            return []

        sub_resp = await client.get(subtitle_url, headers=headers)
        sub_resp.raise_for_status()
        return _segments_from_json_payload(sub_resp.text)


async def _request_player_data(
    client: httpx.AsyncClient,
    signed_params: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    endpoints = (
        ("https://api.bilibili.com/x/player/wbi/v2", signed_params),
        (
            "https://api.bilibili.com/x/player/v2",
            {"aid": signed_params.get("aid"), "cid": signed_params.get("cid")},
        ),
    )
    for endpoint, params in endpoints:
        try:
            resp = await client.get(endpoint, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json() or {}
            data = payload.get("data") or {}
            if data:
                return data
        except Exception:
            continue
    return {}


async def _get_wbi_mixin_key(
    client: httpx.AsyncClient,
    headers: dict[str, str],
) -> str | None:
    try:
        resp = await client.get("https://api.bilibili.com/x/web-interface/nav", headers=headers)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        wbi_img = data.get("wbi_img") or {}
        img_url = str(wbi_img.get("img_url") or "")
        sub_url = str(wbi_img.get("sub_url") or "")
        if not img_url or not sub_url:
            return None
        img_key = img_url.rsplit("/", 1)[-1].split(".", 1)[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".", 1)[0]
        orig = img_key + sub_key
        return "".join(orig[i] for i in _WBI_MIXIN_KEY_ENC_TAB if i < len(orig))[:32]
    except Exception:
        return None


def _wbi_sign(params: dict[str, Any], mixin_key: str) -> dict[str, Any]:
    signed = {**params, "wts": int(time.time())}
    sorted_params = dict(sorted(signed.items()))
    filtered = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted_params.items()}
    query = urllib.parse.urlencode(filtered)
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return signed


async def _fetch_ytdlp_subtitle_segments(url: str) -> list[dict[str, Any]]:
    info = await _extract_ytdlp_info(url)
    if not info:
        return []
    info = _select_playlist_entry(info, url)
    candidates = _subtitle_candidates(info)
    if not candidates:
        return []

    headers = _headers_with_cookie()
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for candidate in candidates:
            try:
                payload = await _subtitle_payload(client, candidate, headers)
                segments = _segments_from_subtitle_payload(payload, str(candidate.get("ext") or ""))
                if segments:
                    return segments
            except Exception as exc:
                logger.debug(f"跳过不可用字幕候选: {exc}")
                continue
    return []


async def _extract_ytdlp_info(url: str) -> dict[str, Any] | None:
    import asyncio
    import yt_dlp

    from app.processor import (
        build_cookie_opts,
        cleanup_temp_cookie,
        is_browser_cookie_error,
        save_browser_cookies_to_cache,
        without_browser_cookie_opts,
    )

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    opts.update(build_cookie_opts())
    browser_cache_path = opts.pop("_browser_cache", None)
    temp_cookie = opts.pop("_temp_cookie", False)
    uses_browser_cookie = "cookiesfrombrowser" in opts

    def _sync_extract(extract_opts: dict[str, Any]) -> dict[str, Any] | None:
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            data = ydl.extract_info(url, download=False)
            if browser_cache_path and ydl.cookiejar:
                try:
                    save_browser_cookies_to_cache(browser_cache_path, ydl.cookiejar)
                except Exception:
                    pass
            return data

    try:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _sync_extract, opts)
        except Exception as exc:
            if uses_browser_cookie and is_browser_cookie_error(exc):
                return await loop.run_in_executor(
                    None,
                    _sync_extract,
                    without_browser_cookie_opts(opts),
                )
            raise
    finally:
        if temp_cookie:
            cleanup_temp_cookie({"cookiefile": opts.get("cookiefile"), "_temp_cookie": True})


def _select_playlist_entry(info: dict[str, Any], url: str) -> dict[str, Any]:
    if info.get("_type") != "playlist" or not info.get("entries"):
        return info

    entries = [entry for entry in info.get("entries") or [] if entry]
    if not entries:
        return info
    idx = min(max(_extract_page(url) - 1, 0), len(entries) - 1)
    return entries[idx] or entries[0]


def _subtitle_candidates(info: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source_rank, field in enumerate(("subtitles", "automatic_captions")):
        subtitle_map = info.get(field) or {}
        if not isinstance(subtitle_map, dict):
            continue
        for lang, items in subtitle_map.items():
            if not isinstance(items, list) or "live_chat" in str(lang).lower():
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidates.append({
                    **item,
                    "_source_rank": source_rank,
                    "_lang": str(lang),
                })

    ext_rank = {"json": 0, "json3": 0, "vtt": 1, "srt": 2, "ass": 3}
    return sorted(
        candidates,
        key=lambda item: (
            _language_rank(str(item.get("_lang") or item.get("name") or "")),
            item.get("_source_rank", 9),
            ext_rank.get(str(item.get("ext") or "").lower(), 9),
        ),
    )


async def _subtitle_payload(
    client: httpx.AsyncClient,
    candidate: dict[str, Any],
    default_headers: dict[str, str],
) -> str:
    data = candidate.get("data")
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    if isinstance(data, str) and data.strip():
        return data

    url = str(candidate.get("url") or "")
    if url.startswith("//"):
        url = f"https:{url}"
    if not url:
        return ""

    headers = dict(default_headers)
    for key, value in (candidate.get("http_headers") or {}).items():
        if isinstance(value, str) and key.lower() not in {"host"}:
            headers[key] = value

    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text


def _language_rank(value: str) -> int:
    lowered = value.lower().replace("_", "-")
    for index, lang in enumerate(_LANG_PRIORITY):
        if lowered == lang or lowered.startswith(f"{lang}-") or lang in lowered:
            return index
    if "zh" in lowered or "chinese" in lowered or "中文" in lowered:
        return 20
    return 100


def _segments_from_subtitle_payload(payload: str, ext: str) -> list[dict[str, Any]]:
    text = payload.lstrip("\ufeff").strip()
    if not text:
        return []

    lower_ext = ext.lower()
    if lower_ext in {"json", "json3"} or text.startswith("{") or text.startswith("["):
        return _segments_from_json_payload(text)
    if lower_ext == "srt" or "-->" in text:
        return _parse_srt_or_vtt(text)
    if lower_ext == "ass" or "[events]" in text.lower():
        return _parse_ass(text)
    return []


def _segments_from_json_payload(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload.lstrip("\ufeff"))
    except json.JSONDecodeError:
        return []

    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, list):
        return _normalize_segments(
            {
                "start": item.get("from", item.get("start", 0)),
                "end": item.get("to", item.get("end", 0)),
                "text": item.get("content", item.get("text", "")),
            }
            for item in body
            if isinstance(item, dict)
        )

    events = data.get("events") if isinstance(data, dict) else None
    if isinstance(events, list):
        segments = []
        for event in events:
            if not isinstance(event, dict):
                continue
            start = float(event.get("tStartMs") or 0) / 1000
            duration = float(event.get("dDurationMs") or 0) / 1000
            text = "".join(
                str(seg.get("utf8") or "")
                for seg in (event.get("segs") or [])
                if isinstance(seg, dict)
            )
            segments.append({"start": start, "end": start + duration, "text": text})
        return _normalize_segments(segments)

    return []


def _parse_srt_or_vtt(payload: str) -> list[dict[str, Any]]:
    text = re.sub(r"^\s*WEBVTT.*?(?:\n\s*\n|\n)", "", payload, flags=re.I | re.S)
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        ts_idx = next((idx for idx, line in enumerate(lines) if "-->" in line), None)
        if ts_idx is None:
            continue
        match = re.match(
            r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{1,3})\s*-->\s*"
            r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{1,3})",
            lines[ts_idx],
        )
        if not match:
            continue
        body = " ".join(lines[ts_idx + 1:])
        segments.append({
            "start": _parse_timestamp(match.group("start")),
            "end": _parse_timestamp(match.group("end")),
            "text": body,
        })
    return _normalize_segments(segments)


def _parse_ass(payload: str) -> list[dict[str, Any]]:
    segments = []
    in_events = False
    format_fields: list[str] | None = None
    for line in payload.splitlines():
        stripped = line.strip()
        if stripped.lower() == "[events]":
            in_events = True
            continue
        if stripped.startswith("[") and in_events:
            break
        if not in_events:
            continue
        if stripped.lower().startswith("format:"):
            format_fields = [field.strip().lower() for field in stripped[7:].split(",")]
            continue
        if stripped.startswith("Dialogue:") and format_fields:
            parts = stripped[9:].split(",", len(format_fields) - 1)
            if len(parts) < len(format_fields):
                continue
            field_map = dict(zip(format_fields, parts))
            body = str(field_map.get("text") or "")
            body = re.sub(r"\{[^}]*}", "", body).replace("\\N", " ").replace("\\n", " ")
            segments.append({
                "start": _parse_timestamp(str(field_map.get("start") or "")),
                "end": _parse_timestamp(str(field_map.get("end") or "")),
                "text": body,
            })
    return _normalize_segments(segments)


def _normalize_segments(items) -> list[dict[str, Any]]:
    segments = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _clean_text(str(item.get("text") or ""))
        if not text:
            continue
        start = _coerce_seconds(item.get("start", 0))
        end = _coerce_seconds(item.get("end", 0))
        if end <= start:
            end = start + 0.01
        segments.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": text,
        })
    return sorted(segments, key=lambda item: (item["start"], item["end"]))


def _clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\\.*?}", "", text)
    text = text.replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def _coerce_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    return _parse_timestamp(str(value))


def _parse_timestamp(value: str) -> float:
    clean = value.strip().split()[0].replace(",", ".")
    if not clean:
        return 0.0
    parts = clean.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
            return max(0.0, hours * 3600 + minutes * 60 + seconds)
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), float(parts[1])
            return max(0.0, minutes * 60 + seconds)
        return max(0.0, float(clean))
    except ValueError:
        return 0.0


def _write_transcript(
    video_dir: str,
    segments: list[dict[str, Any]],
    language: str,
    source: str,
) -> StageResult:
    normalized = _normalize_segments(segments)
    full_text = _full_text(normalized)
    duration = _duration_seconds(normalized)
    video_dir_path = Path(video_dir)
    video_dir_path.mkdir(parents=True, exist_ok=True)

    transcript_json = {
        "language": language,
        "duration_seconds": duration,
        "segments": normalized,
        "full_text": full_text,
        "source": source,
    }
    json_path = video_dir_path / TRANSCRIPT_JSON_NAME
    json_path.write_text(
        json.dumps(transcript_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    srt_path = video_dir_path / TRANSCRIPT_SRT_NAME
    srt_path.write_text(_to_srt(normalized), encoding="utf-8")

    return StageResult(
        success=True,
        artifacts={
            "transcript_json": str(json_path),
            "transcript_srt": str(srt_path),
        },
        metadata={
            "full_text": full_text,
            "language": language,
            "segment_count": len(normalized),
            "duration_seconds": duration,
            "source": source,
        },
    )


def _full_text(segments: list[dict[str, Any]]) -> str:
    return " ".join(str(segment.get("text") or "").strip() for segment in segments).strip()


def _duration_seconds(segments: list[dict[str, Any]]) -> float:
    return round(max((float(segment.get("end") or 0) for segment in segments), default=0.0), 2)


def _to_srt(segments: list[dict[str, Any]]) -> str:
    lines = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_fmt_srt_time(segment['start'])} --> {_fmt_srt_time(segment['end'])}")
        lines.append(str(segment.get("text") or ""))
        lines.append("")
    return "\n".join(lines)


def _fmt_srt_time(seconds: float) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = int(value % 60)
    millis = int(round((value - int(value)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
