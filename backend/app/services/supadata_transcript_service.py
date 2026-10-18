import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.video import TranscriptSegment
from app.services.transcription_service import (
    TranscriptionResult,
    transcript_segments_from_plain_text,
)


SUPADATA_API_BASE = "https://api.supadata.ai/v1"


class SupadataTranscriptUnavailableError(Exception):
    """Raised when Supadata cannot produce a transcript for a video URL."""


def transcribe_video_url_with_supadata(url: str) -> TranscriptionResult:
    settings = get_settings()
    api_key = (settings.supadata_api_key or "").strip()
    mode = settings.supadata_transcript_mode

    if not api_key:
        raise SupadataTranscriptUnavailableError(
            "Supadata API key is not configured."
        )

    payload = _fetch_transcript_payload(
        url=url,
        api_key=api_key,
        mode=mode,
        timeout_seconds=settings.supadata_transcript_timeout_seconds,
    )
    segments = _segments_from_payload(payload)

    if not segments:
        raise SupadataTranscriptUnavailableError(
            "Supadata returned no transcript segments."
        )

    language = _optional_string(payload.get("lang"))

    native_captions_only = mode == "native"
    return TranscriptionResult(
        segments=segments,
        transcript_language=language,
        detected_language=language,
        transcript_source=(
            "supadata_platform_captions"
            if native_captions_only
            else "supadata_managed_transcript"
        ),
        transcript_source_note=(
            "Transcript extracted from available platform captions through the "
            "configured Supadata fallback."
            if native_captions_only
            else "Transcript produced through the configured Supadata fallback."
        ),
    )


def _fetch_transcript_payload(
    *, url: str, api_key: str, mode: str, timeout_seconds: int
) -> dict[str, Any]:
    timeout = max(timeout_seconds, 10)
    deadline = time.monotonic() + timeout
    headers = {"x-api-key": api_key}

    try:
        client_timeout = httpx.Timeout(float(timeout), connect=10.0)
        with httpx.Client(timeout=client_timeout) as client:
            response = client.get(
                f"{SUPADATA_API_BASE}/transcript",
                headers=headers,
                params={"url": url, "mode": mode, "text": "false"},
            )
            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError("Unexpected Supadata response shape.")

            job_id = _optional_string(payload.get("jobId"))
            if not job_id:
                return payload

            return _poll_transcript_job(
                client=client,
                job_id=job_id,
                headers=headers,
                deadline=deadline,
            )
    except SupadataTranscriptUnavailableError:
        raise
    except httpx.HTTPStatusError as exc:
        raise SupadataTranscriptUnavailableError(
            f"Supadata transcript request returned HTTP {exc.response.status_code}."
        ) from None
    except (httpx.HTTPError, ValueError):
        raise SupadataTranscriptUnavailableError(
            "Supadata transcript request failed or returned invalid data."
        ) from None


def _poll_transcript_job(
    *,
    client: httpx.Client,
    job_id: str,
    headers: dict[str, str],
    deadline: float,
) -> dict[str, Any]:
    while time.monotonic() < deadline:
        response = client.get(
            f"{SUPADATA_API_BASE}/transcript/{job_id}", headers=headers
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Unexpected Supadata job response shape.")

        status = str(payload.get("status") or "").strip().lower()
        if status == "failed":
            raise SupadataTranscriptUnavailableError(
                "Supadata transcript job failed."
            )

        result = payload.get("result")
        if status == "completed" and isinstance(result, dict):
            return result

        if "content" in payload:
            return payload

        time.sleep(1.0)

    raise SupadataTranscriptUnavailableError("Supadata transcript request timed out.")


def _segments_from_payload(payload: dict[str, Any]) -> list[TranscriptSegment]:
    content = payload.get("content")

    if isinstance(content, str):
        return transcript_segments_from_plain_text(content)

    if not isinstance(content, list):
        return []

    segments: list[TranscriptSegment] = []
    for item in content:
        if not isinstance(item, dict):
            continue

        text = _optional_string(item.get("text"))
        if not text:
            continue

        start_time = _milliseconds_to_seconds(item.get("offset"))
        duration = _milliseconds_to_seconds(item.get("duration"))
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
                text=text,
            )
        )

    return segments


def _milliseconds_to_seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) / 1000
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
