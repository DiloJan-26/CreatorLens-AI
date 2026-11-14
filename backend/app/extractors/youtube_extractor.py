from dataclasses import replace
import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL

from app.core.config import get_settings
from app.extractors.metadata_normalizer import extract_best_audio_url, normalize_metadata
from app.services.evidence_quality import language_matches, language_code, assess_transcript
from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata
from app.services.apify_transcript_service import (
    ApifyTranscriptUnavailableError,
    transcribe_youtube_url_with_apify,
)
from app.services.supadata_transcript_service import (
    SupadataTranscriptUnavailableError,
    transcribe_video_url_with_supadata,
)
from app.services.transcription_service import (
    TranscriptionResult,
    TranscriptionUnavailableError,
    transcribe_audio_url_with_deepgram,
)


HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")
_YT_API_BASE = "https://www.googleapis.com/youtube/v3"

YOUTUBE_METRIC_SOURCE_NOTE = (
    "YouTube counts are extracted from public metadata and may differ slightly "
    "from the live UI because of rounding, caching, timezone, or updates."
)
YOUTUBE_TRANSCRIPT_AVAILABLE_NOTE = (
    "Transcript extracted from YouTube captions/subtitles when available."
)
YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE = (
    "Transcript unavailable because no captions were found and public media audio could not be extracted."
)
TRANSCRIPT_COMPLETENESS_RATIO = 0.92
TRANSCRIPT_COMPLETENESS_GAP_SECONDS = 1.5

logger = logging.getLogger(__name__)


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
    from app.extraction.policy import block_legacy_provider
    block_legacy_provider()
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


def fetch_youtube_info_from_api(video_id: str, api_key: str) -> dict[str, Any]:
    """Fetch YouTube metadata via the official Data API v3.

    Returns a dict with the same keys normalize_metadata expects from yt-dlp,
    so the rest of the pipeline works unchanged.
    """
    from app.extraction.policy import block_legacy_provider
    block_legacy_provider()
    with httpx.Client(timeout=15.0) as client:
        video_resp = client.get(
            f"{_YT_API_BASE}/videos",
            params={
                "id": video_id,
                "part": "snippet,statistics,contentDetails",
            },
            headers={"X-Goog-Api-Key": api_key},
        )
        video_resp.raise_for_status()
        video_data = video_resp.json()

    items = video_data.get("items", [])
    if not items:
        raise ValueError(f"YouTube Data API returned no item for video ID {video_id!r}.")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    content_details = item.get("contentDetails", {})

    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = (
        thumbnails.get("maxres", {}).get("url")
        or thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
    )

    channel_id = snippet.get("channelId")
    subscriber_count = _fetch_subscriber_count(channel_id, api_key) if channel_id else None

    return {
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "uploader": snippet.get("channelTitle"),
        "channel": snippet.get("channelTitle"),
        "channel_id": channel_id,
        "uploader_id": channel_id,
        "view_count": _safe_int(statistics.get("viewCount")),
        "like_count": _safe_int(statistics.get("likeCount")),
        "comment_count": _safe_int(statistics.get("commentCount")),
        "channel_follower_count": subscriber_count,
        "subscriber_count": subscriber_count,
        "duration": _parse_iso_duration(content_details.get("duration", "")),
        "upload_date": _parse_publish_date(snippet.get("publishedAt", "")),
        "thumbnail": thumbnail_url,
        "tags": snippet.get("tags") or [],
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def _fetch_subscriber_count(channel_id: str, api_key: str) -> int | None:
    from app.extraction.policy import block_legacy_provider
    block_legacy_provider()
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{_YT_API_BASE}/channels",
                params={"id": channel_id, "part": "statistics"},
                headers={"X-Goog-Api-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("items", [])
        if items:
            return _safe_int(items[0].get("statistics", {}).get("subscriberCount"))
    except Exception:
        pass
    return None


def _parse_iso_duration(duration: str) -> int | None:
    """Convert ISO 8601 duration (PT#H#M#S) to total seconds."""
    if not duration:
        return None
    match = re.match(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        duration,
    )
    if not match:
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(float(match.group(4) or 0))
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def _parse_publish_date(published_at: str) -> str | None:
    """Convert ISO 8601 datetime to YYYYMMDD (yt-dlp upload_date format)."""
    if not published_at or len(published_at) < 10:
        return None
    return published_at[:10].replace("-", "")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def fetch_youtube_metadata(url: str) -> dict[str, Any]:
    return normalize_metadata(
        platform="youtube",
        url=url,
        info=fetch_youtube_info(url),
        metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
        transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
    ).model_dump()


def fetch_youtube_transcript(video_id: str) -> list[TranscriptSegment]:
    return fetch_youtube_transcript_with_metadata(video_id).segments


def fetch_youtube_transcript_with_metadata(video_id: str, original_audio_language: str | None = None) -> TranscriptionResult:
    raw_items, language, provenance = _select_caption_items(video_id, original_audio_language)
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

    if not segments:
        return TranscriptionResult(
            segments=[],
            transcript_source="unavailable",
            transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
            provenance=provenance,
        )

    return TranscriptionResult(
        segments=segments,
        transcript_language=language,
        detected_language=None,
        provenance=provenance,
        transcript_source="platform_captions",
        transcript_source_note=(
            "Transcript extracted from YouTube captions/subtitles. "
            f"Language: {language or 'unknown'}."
        ),
    )


def extract_youtube_video(url: str) -> VideoExtractionResult:
    # Step 1: Extract video ID — if this fails, nothing else can proceed.
    try:
        video_id = extract_youtube_video_id(url)
    except Exception as exc:
        return VideoExtractionResult(
            metadata=VideoMetadata(
                platform="youtube",
                url=url,
                extraction_status="failed",
                error_message=_safe_error_message(exc),
                transcript_source="unavailable",
                metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
                transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
            ),
            transcript_segments=[],
        )

    # Step 2: Fetch metadata.
    # Priority: YouTube Data API v3 (works on cloud, needs YOUTUBE_API_KEY)
    #           → yt-dlp (works locally, blocked on cloud datacenter IPs)
    settings = get_settings()
    youtube_api_key = (settings.youtube_api_key or "").strip()
    info: dict[str, Any] | None = None
    yt_dlp_error: str | None = None
    info_from_ytdlp = False

    if youtube_api_key:
        try:
            info = fetch_youtube_info_from_api(video_id, youtube_api_key)
        except Exception:
            pass  # Fall through to yt-dlp

    if info is None:
        try:
            info = fetch_youtube_info(url)
            info_from_ytdlp = True
        except Exception as exc:
            yt_dlp_error = _safe_error_message(exc)

    expected_duration = _expected_duration_seconds(info)

    # Attempt captions directly before using a managed fallback.
    original_language = language_code((info or {}).get("default_audio_language"))
    transcript_result = fetch_youtube_transcript_with_metadata(video_id, original_language)
    transcript_result = _with_audio_context(transcript_result, original_language)

    # Prefer Supadata when configured. Apify remains a legacy fallback only
    # when Supadata is absent, preventing paid actor starts after migration.
    supadata_configured = bool((settings.supadata_api_key or "").strip())
    if (
        supadata_configured
        and _should_try_transcript_fallback(transcript_result, expected_duration)
    ):
        try:
            transcript_result = _better_transcript_result(
                current=transcript_result,
                candidate=_with_audio_context(transcribe_video_url_with_supadata(url), original_language),
                expected_duration=expected_duration,
            )
        except SupadataTranscriptUnavailableError as exc:
            logger.warning("Supadata transcript fallback unavailable: %s", exc)

    if (
        not supadata_configured
        and _should_try_transcript_fallback(transcript_result, expected_duration)
    ):
        try:
            transcript_result = _better_transcript_result(
                current=transcript_result,
                candidate=_with_audio_context(transcribe_youtube_url_with_apify(url), original_language),
                expected_duration=expected_duration,
            )
        except ApifyTranscriptUnavailableError as exc:
            logger.warning("Apify transcript fallback unavailable: %s", exc)

    # Step 4: Audio transcription fallback — only when yt-dlp provided the info
    # (audio format URLs are yt-dlp specific; YouTube Data API v3 doesn't supply them).
    # If metadata came from the Data API, make a separate best-effort yt-dlp
    # request just for audio before giving up on transcript evidence.
    if _should_try_transcript_fallback(transcript_result, expected_duration):
        audio_info = info if info_from_ytdlp else _fetch_youtube_audio_info(url)

        if audio_info is not None:
            transcript_result = _better_transcript_result(
                current=transcript_result,
                candidate=_transcribe_youtube_audio(audio_info),
                expected_duration=expected_duration,
            )

    if _known_mismatch(transcript_result):
        transcript_result = replace(transcript_result, segments=[], transcript_source_note="Caption language conflicts with original-audio metadata; transcript unavailable.")
    transcript_segments = transcript_result.segments
    transcript_available = len(transcript_segments) > 0

    if info is None:
        # yt-dlp was blocked — partial extraction with captions only.
        extraction_status = "partial" if transcript_available else "failed"
        error_message = (
            None
            if transcript_available
            else (
                "YouTube public metadata could not be extracted "
                f"({yt_dlp_error or 'yt-dlp blocked'}). "
                "No captions were available either."
            )
        )
        transcript_source_note = (
            transcript_result.transcript_source_note
            or YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE
        )
    else:
        extraction_status = "ready" if transcript_available else "partial"
        error_message = (
            None
            if transcript_available
            else "YouTube metadata extracted, but transcript was unavailable."
        )
        transcript_source_note = (
            transcript_result.transcript_source_note
            or YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE
        )

    video_metadata = normalize_metadata(
        platform="youtube",
        url=url,
        info=info or {},
        transcript_available=transcript_available,
        transcript_segment_count=len(transcript_segments),
        transcript_language=transcript_result.transcript_language,
        detected_language=transcript_result.detected_language,
        language_confidence=transcript_result.language_confidence,
        transcript_source=transcript_result.transcript_source,
        extraction_status=extraction_status,
        error_message=error_message,
        metric_source_note=YOUTUBE_METRIC_SOURCE_NOTE,
        transcript_source_note=transcript_source_note,
    )

    video_metadata.transcript_evidence = {"provenance": transcript_result.provenance}
    return VideoExtractionResult(
        metadata=video_metadata,
        transcript_segments=transcript_segments,
    )


def _with_audio_context(result: TranscriptionResult, original_language: str | None) -> TranscriptionResult:
    provenance = dict(result.provenance)
    if result.transcript_source == "deepgram_multilingual":
        provenance.update(original_audio_language=result.detected_language,
                          audio_language_source="deepgram_audio_analysis",
                          audio_language_verified=bool(result.detected_language))
    else:
        provenance.setdefault("original_audio_language", original_language)
        provenance.setdefault("audio_language_source", "youtube_default_audio_language" if original_language else "unknown")
        provenance.setdefault("audio_language_verified", False)
        provenance.setdefault("caption_track_language", result.transcript_language)
        provenance.setdefault("caption_kind", "unknown")
    return replace(result, provenance=provenance)


def _known_mismatch(result: TranscriptionResult) -> bool:
    p = result.provenance
    audio = p.get("original_audio_language")
    track = p.get("caption_track_language")
    return bool(audio and track and not language_matches(audio, track))


def _select_caption_items(video_id: str, original_audio_language: str | None = None):
    from app.extraction.policy import block_legacy_provider
    block_legacy_provider()
    requested = get_settings().transcript_fallback_language_list or ["en", "hi", "ta"]
    preferred = [original_audio_language] if original_audio_language else requested
    provenance = {"requested_languages": requested, "original_audio_language": original_audio_language,
        "audio_language_source": "youtube_default_audio_language" if original_audio_language else "unknown",
        "audio_language_verified": False, "caption_kind": "unknown",
        "detected_text_language": None}
    try:
        try:
            tracks = list(YouTubeTranscriptApi().list(video_id))
        except Exception:
            tracks = list(getattr(YouTubeTranscriptApi, "list_transcripts")(video_id))
        provenance["available_track_languages"] = [_transcript_language(t) for t in tracks]
        candidates = [t for t in tracks if any(language_matches(_transcript_language(t), l) for l in preferred)]
        if not candidates:
            # Never fetch an arbitrary language solely because it was listed first.
            provenance["selection_reason"] = "no_compatible_language_track"
            return [], None, provenance
        candidates.sort(key=lambda t: (
            next((i for i, l in enumerate(preferred) if language_matches(_transcript_language(t), l)), 999),
            bool(getattr(t, "is_translated", False)), bool(getattr(t, "is_generated", False)),
            _transcript_language(t) or ""))
        for track in candidates:
            try:
                fetched = track.fetch()
            except Exception:
                continue
            language = _transcript_language(track)
            kind = "translated" if getattr(track, "is_translated", False) else (
                "automatic" if getattr(track, "is_generated", None) is True else
                "original" if getattr(track, "is_generated", None) is False and original_audio_language else "unknown")
            provenance.update(caption_track_language=language, caption_kind=kind,
                caption_generation="automatic" if getattr(track, "is_generated", None) is True else "manual" if getattr(track, "is_generated", None) is False else "unknown",
                selection_reason="original_audio_language_match" if original_audio_language else "requested_language_match_audio_unverified")
            return fetched, language, provenance
        provenance["selection_reason"] = "compatible_tracks_failed"
        return [], None, provenance
    except Exception:
        # Older API versions expose fetch only. Request languages explicitly, but
        # do not pretend requested language is the actual returned track language.
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=preferred)
        except Exception:
            try:
                fetched = getattr(YouTubeTranscriptApi, "get_transcript")(video_id, languages=preferred)
            except Exception:
                provenance["selection_reason"] = "caption_provider_unavailable"
                return [], None, provenance
        actual = getattr(fetched, "language_code", None)
        provenance.update(caption_track_language=actual, selection_reason="legacy_fetch_track_metadata_limited")
        return fetched, actual, provenance


def _fetch_transcript_items(video_id: str):
    items, language, _ = _select_caption_items(video_id)
    return items, language


def _fetch_transcript_from_list_api(video_id: str, languages: list[str]):
    items, language, _ = _select_caption_items(video_id, languages[0] if len(languages) == 1 else None)
    return (items, language) if items else None


def _transcribe_youtube_audio(info: dict[str, Any]) -> TranscriptionResult:
    audio_url = extract_best_audio_url(info)

    if not audio_url:
        return TranscriptionResult(
            segments=[],
            transcript_source="unavailable",
            transcript_source_note=YOUTUBE_TRANSCRIPT_UNAVAILABLE_NOTE,
        )

    try:
        return transcribe_audio_url_with_deepgram(audio_url)
    except TranscriptionUnavailableError:
        return TranscriptionResult(
            segments=[],
            transcript_source="unavailable",
            transcript_source_note=(
                "Transcript unavailable because audio transcription failed or public media audio could not be extracted."
            ),
        )


def _fetch_youtube_audio_info(url: str) -> dict[str, Any] | None:
    try:
        return fetch_youtube_info(url)
    except Exception:
        return None


def _expected_duration_seconds(info: dict[str, Any] | None) -> float | None:
    if not info:
        return None

    duration = info.get("duration")

    if isinstance(duration, bool):
        return None

    if isinstance(duration, int | float) and duration > 0:
        return float(duration)

    return None


def _should_try_transcript_fallback(
    transcript_result: TranscriptionResult,
    expected_duration: float | None,
) -> bool:
    _, quality = assess_transcript(transcript_result.segments, duration=expected_duration,
        provenance=transcript_result.provenance, source=transcript_result.transcript_source)
    if quality["status"] == "invalid":
        return True
    if _known_mismatch(transcript_result) or transcript_result.provenance.get("caption_kind") == "translated":
        return True
    if not transcript_result.segments:
        return True

    if expected_duration is None or expected_duration <= 0:
        return False

    coverage = _transcript_coverage_seconds(transcript_result.segments)

    if coverage is None:
        return False

    remaining_gap = expected_duration - coverage

    return (
        remaining_gap > TRANSCRIPT_COMPLETENESS_GAP_SECONDS
        and coverage / expected_duration < TRANSCRIPT_COMPLETENESS_RATIO
    )


def _better_transcript_result(
    *,
    current: TranscriptionResult,
    candidate: TranscriptionResult,
    expected_duration: float | None,
) -> TranscriptionResult:
    _, quality = assess_transcript(candidate.segments, duration=expected_duration,
        provenance=candidate.provenance, source=candidate.transcript_source)
    if quality["status"] == "invalid":
        return current
    if not candidate.segments or _known_mismatch(candidate):
        return current
    if _known_mismatch(current):
        return candidate
    if current.provenance.get("caption_kind") == "translated" and candidate.provenance.get("caption_kind") in {"original", "automatic"}:
        return candidate

    if not current.segments:
        return candidate

    current_score = _transcript_completeness_score(current.segments, expected_duration)
    candidate_score = _transcript_completeness_score(candidate.segments, expected_duration)

    if candidate_score > current_score:
        return candidate

    return current


def _transcript_completeness_score(
    segments: list[TranscriptSegment],
    expected_duration: float | None,
) -> tuple[float, int, int]:
    coverage = _transcript_coverage_seconds(segments)
    coverage_ratio = 0.0

    if coverage is not None:
        if expected_duration and expected_duration > 0:
            coverage_ratio = min(coverage / expected_duration, 1.0)
        else:
            coverage_ratio = coverage

    text_length = sum(len(segment.text.strip()) for segment in segments)

    return coverage_ratio, text_length, len(segments)


def _transcript_coverage_seconds(
    segments: list[TranscriptSegment],
) -> float | None:
    end_times = [
        segment.end_time
        for segment in segments
        if isinstance(segment.end_time, int | float)
    ]

    if not end_times:
        return None

    return max(float(end_time) for end_time in end_times)


def _transcript_language(transcript: Any) -> str | None:
    for attribute in ("language_code", "language"):
        value = getattr(transcript, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


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
