import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL

from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata
from app.services.metrics_service import calculate_engagement_rate


HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if len(path_parts) >= 2 and path_parts[0] == "shorts":
            return path_parts[1]

        if parsed.path == "/watch":
            video_ids = parse_qs(parsed.query).get("v")
            if video_ids and video_ids[0].strip():
                return video_ids[0].strip()

    if host == "youtu.be" and path_parts:
        return path_parts[0]

    raise ValueError("Could not find a YouTube video ID in the URL.")


def extract_hashtags(
    title: str | None,
    description: str | None,
    tags: list[str] | None,
) -> list[str]:
    collected: list[str] = []

    for text in (title, description):
        if text:
            collected.extend(HASHTAG_PATTERN.findall(text))

    if tags:
        collected.extend(tags)

    seen: set[str] = set()
    normalized: list[str] = []

    for tag in collected:
        clean_tag = tag.strip().lstrip("#").lower()

        if not clean_tag or clean_tag in seen:
            continue

        seen.add(clean_tag)
        normalized.append(clean_tag)

    return normalized


def fetch_youtube_metadata(url: str) -> dict[str, Any]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise ValueError("Could not read YouTube metadata.")

    title = _as_optional_string(info.get("title"))
    description = _as_optional_string(info.get("description"))
    tags = _as_string_list(info.get("tags"))

    return {
        "title": title,
        "creator": _as_optional_string(info.get("channel"))
        or _as_optional_string(info.get("uploader")),
        "views": _as_optional_int(info.get("view_count")),
        "likes": _as_optional_int(info.get("like_count")),
        "comments": _as_optional_int(info.get("comment_count")),
        "duration_seconds": _as_optional_int(info.get("duration")),
        "upload_date": _format_upload_date(info.get("upload_date")),
        "description": description,
        "tags": tags,
        "hashtags": extract_hashtags(title, description, tags),
        "webpage_url": _as_optional_string(info.get("webpage_url")),
    }


def fetch_youtube_transcript(video_id: str) -> list[TranscriptSegment]:
    raw_items = _fetch_transcript_items(video_id)
    segments: list[TranscriptSegment] = []

    for item in raw_items:
        text = _get_transcript_value(item, "text")

        if not isinstance(text, str) or not text.strip():
            continue

        start_time = _as_optional_float(_get_transcript_value(item, "start"))
        duration = _as_optional_float(_get_transcript_value(item, "duration"))
        end_time = (
            start_time + duration
            if start_time is not None and duration is not None
            else None
        )

        segments.append(
            TranscriptSegment(
                segment_index=len(segments),
                start_time=start_time,
                end_time=end_time,
                text=text.strip(),
            )
        )

    return segments


def extract_youtube_video(url: str) -> VideoExtractionResult:
    try:
        video_id = extract_youtube_video_id(url)
        metadata = fetch_youtube_metadata(url)
        transcript_segments = fetch_youtube_transcript(video_id)
    except Exception as exc:
        return VideoExtractionResult(
            metadata=VideoMetadata(
                platform="youtube",
                url=url,
                extraction_status="failed",
                error_message=_safe_error_message(exc),
            ),
            transcript_segments=[],
        )

    views = metadata.get("views")
    likes = metadata.get("likes")
    comments = metadata.get("comments")

    video_metadata = VideoMetadata(
        platform="youtube",
        url=metadata.get("webpage_url") or url,
        title=metadata.get("title"),
        creator=metadata.get("creator"),
        follower_count=None,
        views=views,
        likes=likes,
        comments=comments,
        hashtags=metadata.get("hashtags") or [],
        upload_date=metadata.get("upload_date"),
        duration_seconds=metadata.get("duration_seconds"),
        engagement_rate=calculate_engagement_rate(likes, comments, views),
        transcript_available=len(transcript_segments) > 0,
        transcript_segment_count=len(transcript_segments),
        extraction_status="ready",
        error_message=None,
    )

    return VideoExtractionResult(
        metadata=video_metadata,
        transcript_segments=transcript_segments,
    )


def _fetch_transcript_items(video_id: str) -> Iterable[Any]:
    try:
        api = YouTubeTranscriptApi()
        return api.fetch(video_id, languages=["en"])
    except Exception:
        pass

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        try:
            transcript = transcript_list.find_transcript(["en"])
        except Exception:
            transcript = next(iter(transcript_list))

        return transcript.fetch()
    except Exception:
        pass

    try:
        get_transcript = getattr(YouTubeTranscriptApi, "get_transcript")
        return get_transcript(video_id, languages=["en"])
    except Exception:
        pass

    try:
        list_transcripts = getattr(YouTubeTranscriptApi, "list_transcripts")
        transcript_list = list_transcripts(video_id)

        try:
            transcript = transcript_list.find_transcript(["en"])
        except Exception:
            transcript = next(iter(transcript_list))

        return transcript.fetch()
    except Exception:
        return []


def _get_transcript_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)

    return getattr(item, key, None)


def _format_upload_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        return None

    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _as_optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _as_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None

    return [item for item in value if isinstance(item, str) and item.strip()]


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    return None


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return (message or "YouTube extraction failed.")[:200]
