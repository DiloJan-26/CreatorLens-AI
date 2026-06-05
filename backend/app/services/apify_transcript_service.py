from typing import Any

import httpx

from app.core.config import get_settings
from app.models.video import TranscriptSegment
from app.services.transcription_service import (
    TranscriptionResult,
    transcript_segments_from_plain_text,
)


APIFY_API_BASE = "https://api.apify.com/v2"


class ApifyTranscriptUnavailableError(Exception):
    """Raised when Apify cannot produce a transcript for a YouTube URL."""


def transcribe_youtube_url_with_apify(url: str) -> TranscriptionResult:
    settings = get_settings()
    token = (settings.apify_api_token or "").strip()

    if not token:
        raise ApifyTranscriptUnavailableError("Apify API token is not configured.")

    actor = settings.apify_youtube_transcript_actor.strip()
    if not actor:
        raise ApifyTranscriptUnavailableError(
            "Apify YouTube transcript actor is not configured."
        )

    items = _run_actor(
        actor=actor,
        token=token,
        url=url,
        input_style=settings.apify_youtube_transcript_input_style,
        timeout_seconds=settings.apify_youtube_transcript_timeout_seconds,
    )
    segments = _segments_from_items(items)

    if not segments:
        raise ApifyTranscriptUnavailableError("Apify returned no transcript segments.")

    return TranscriptionResult(
        segments=segments,
        transcript_source="apify_youtube_transcript",
        transcript_source_note=(
            "Transcript extracted through the configured Apify YouTube transcript "
            "fallback actor."
        ),
    )


def _run_actor(
    *,
    actor: str,
    token: str,
    url: str,
    input_style: str,
    timeout_seconds: int,
) -> list[Any]:
    actor_id = actor.replace("/", "~")
    endpoint = f"{APIFY_API_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = _actor_input(url=url, input_style=input_style)

    try:
        response = httpx.post(
            endpoint,
            params={"token": token, "timeout": max(timeout_seconds, 30)},
            json=payload,
            timeout=httpx.Timeout(float(max(timeout_seconds, 30)) + 15, connect=10.0),
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise ApifyTranscriptUnavailableError(
            "Apify transcript actor failed or returned invalid data."
        ) from None

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("items", "data", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def _actor_input(url: str, input_style: str) -> dict[str, Any]:
    style = input_style.strip() or "videoUrls"

    if style == "urls":
        return {"urls": [url]}

    if style == "startUrls":
        return {"startUrls": [{"url": url}]}

    return {
        "mode": "url",
        "videoUrls": [url],
    }


def _segments_from_items(items: list[Any]) -> list[TranscriptSegment]:
    aggregated_segments = _segments_from_list(items)

    if aggregated_segments:
        return _reindex_segments(aggregated_segments)

    candidates: list[list[TranscriptSegment]] = []

    for item in items:
        segments = _segments_from_item(item)

        if segments:
            candidates.append(segments)

    if not candidates:
        return []

    return _reindex_segments(max(candidates, key=_segments_score))


def _segments_from_item(item: Any) -> list[TranscriptSegment]:
    if isinstance(item, str):
        return transcript_segments_from_plain_text(item)

    if isinstance(item, list):
        return _segments_from_list(item)

    if not isinstance(item, dict):
        return []

    for key in (
        "segments",
        "transcriptSegments",
        "transcript_segments",
        "captions",
        "subtitles",
        "timestamps",
        "transcript",
    ):
        value = item.get(key)

        if isinstance(value, list):
            segments = _segments_from_list(value)
            if segments:
                return segments

        if isinstance(value, str):
            segments = transcript_segments_from_plain_text(value)
            if segments:
                return segments

    for key in ("text", "content", "fullText", "full_text", "transcriptText"):
        value = item.get(key)

        if isinstance(value, str):
            segments = transcript_segments_from_plain_text(value)
            if segments:
                return segments

    return []


def _segments_from_list(values: list[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    plain_parts: list[str] = []

    for value in values:
        if isinstance(value, str) and value.strip():
            plain_parts.append(value.strip())
            continue

        if not isinstance(value, dict):
            continue

        text = _text_from_segment(value)

        if not text:
            continue

        segments.append(
            TranscriptSegment(
                segment_index=len(segments),
                start_time=_time_value(
                    _first_value(value, ("start", "startTime", "start_time", "from"))
                ),
                end_time=_end_time(value),
                text=text,
            )
        )

    if segments:
        return segments

    return transcript_segments_from_plain_text(" ".join(plain_parts))


def _text_from_segment(value: dict[str, Any]) -> str | None:
    raw_text = _first_value(
        value,
        (
            "text",
            "caption",
            "subtitle",
            "sentence",
            "transcript",
            "content",
            "line",
        ),
    )

    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text.strip()

    return None


def _end_time(value: dict[str, Any]) -> float | None:
    end_time = _time_value(
        _first_value(value, ("end", "endTime", "end_time", "to"))
    )

    if end_time is not None:
        return end_time

    start_time = _time_value(
        _first_value(value, ("start", "startTime", "start_time", "from"))
    )
    duration = _time_value(_first_value(value, ("duration", "dur")))

    if start_time is not None and duration is not None:
        return start_time + duration

    return None


def _first_value(value: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in value:
            return value[key]

    return None


def _time_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        number = float(value)
        return number / 1000 if number > 10000 else number

    if not isinstance(value, str):
        return None

    text = value.strip()

    if not text:
        return None

    try:
        number = float(text)
        return number / 1000 if number > 10000 else number
    except ValueError:
        pass

    parts = text.split(":")

    if not all(part.replace(".", "", 1).isdigit() for part in parts):
        return None

    seconds = 0.0

    for part in parts:
        seconds = seconds * 60 + float(part)

    return seconds


def _reindex_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            segment_index=index,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text,
        )
        for index, segment in enumerate(segments)
    ]


def _segments_score(segments: list[TranscriptSegment]) -> tuple[float, int, int]:
    end_times = [
        segment.end_time
        for segment in segments
        if isinstance(segment.end_time, int | float)
    ]
    coverage = max(end_times) if end_times else 0.0
    text_length = sum(len(segment.text.strip()) for segment in segments)

    return float(coverage), text_length, len(segments)
