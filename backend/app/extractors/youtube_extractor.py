import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL

from app.extractors.metadata_normalizer import normalize_metadata
from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata


HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")
YOUTUBE_METRIC_SOURCE_NOTE = (
    "YouTube counts are extracted from public metadata and may differ slightly "
    "from the live UI because of rounding, caching, timezone, or updates."
)
YOUTUBE_TRANSCRIPT_AVAILABLE_NOTE = (
    "Transcript extracted from YouTube captions/subtitles when available."
)
YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE = (
    "YouTube captions/subtitles were unavailable for this video."
)


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


def fetch_youtube_info(url: str) -> dict[str, Any]:
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

    return info


def fetch_youtube_metadata(url: str) -> dict[str, Any]:
    return normalize_metadata(
        platform="youtube",
        url=url,
        info=fetch_youtube_info(url),
        metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
        transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
    ).model_dump()


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
        info = fetch_youtube_info(url)
        transcript_segments = fetch_youtube_transcript(video_id)
    except Exception as exc:
        return VideoExtractionResult(
            metadata=VideoMetadata(
                platform="youtube",
                url=url,
                extraction_status="failed",
                error_message=_safe_error_message(exc),
                metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
                transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
            ),
            transcript_segments=[],
        )

    transcript_available = len(transcript_segments) > 0

    video_metadata = normalize_metadata(
        platform="youtube",
        url=url,
        info=info,
        transcript_available=transcript_available,
        transcript_segment_count=len(transcript_segments),
        extraction_status="ready",
        error_message=None,
        metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
        transcript_source_note=(
            YOUTUBE_TRANSCRIPT_AVAILABLE_NOTE
            if transcript_available
            else YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE
        ),
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
