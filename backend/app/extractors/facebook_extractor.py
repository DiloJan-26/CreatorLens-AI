from typing import Any

from yt_dlp import YoutubeDL

from app.extractors.metadata_normalizer import (
    PLATFORM_METRIC_NOTES,
    extract_best_audio_url,
    normalize_metadata,
)
from app.models.video import VideoExtractionResult, VideoMetadata
from app.services.transcription_service import (
    TranscriptionUnavailableError,
    transcribe_audio_url_with_deepgram,
)


FACEBOOK_TRANSCRIPT_AVAILABLE_NOTE = (
    "Facebook transcript generated from public media audio using Deepgram when "
    "media was available."
)
FACEBOOK_TRANSCRIPT_UNAVAILABLE_NOTE = (
    "Facebook transcript unavailable because public media audio could not be "
    "extracted."
)


def extract_facebook_content(
    url: str,
    project_id: str | None = None,
    slot: str | None = None,
) -> VideoExtractionResult:
    try:
        info = fetch_facebook_info(url)
    except Exception as exc:
        return VideoExtractionResult(
            metadata=_failed_facebook_metadata(url=url, slot=slot, message=str(exc)),
            transcript_segments=[],
        )

    audio_url = extract_best_audio_url(info)
    transcript_segments = []

    if audio_url:
        try:
            transcript_segments = transcribe_audio_url_with_deepgram(audio_url)
        except TranscriptionUnavailableError:
            transcript_segments = []

    transcript_available = bool(transcript_segments)
    metadata = normalize_metadata(
        platform="facebook",
        url=url,
        info=info,
        slot=slot,
        transcript_available=transcript_available,
        transcript_segment_count=len(transcript_segments),
        extraction_status="ready" if transcript_available else "partial",
        error_message=(
            None
            if transcript_available
            else "Facebook metadata extracted, but transcript was unavailable."
        ),
        metric_source_note=PLATFORM_METRIC_NOTES["facebook"],
        transcript_source_note=(
            FACEBOOK_TRANSCRIPT_AVAILABLE_NOTE
            if transcript_available
            else FACEBOOK_TRANSCRIPT_UNAVAILABLE_NOTE
        ),
    )

    return VideoExtractionResult(
        metadata=metadata,
        transcript_segments=transcript_segments,
    )


def fetch_facebook_info(url: str) -> dict[str, Any]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise ValueError(
            f"Facebook public extraction failed: {_safe_error_message(str(exc))}"
        ) from None

    if not isinstance(info, dict):
        raise ValueError("Facebook public extraction returned no usable data.")

    return info


def _failed_facebook_metadata(
    *,
    url: str,
    slot: str | None,
    message: str,
) -> VideoMetadata:
    return VideoMetadata(
        slot=slot,  # type: ignore[arg-type]
        platform="facebook",
        url=url,
        extraction_status="failed",
        error_message=_safe_error_message(message),
        transcript_available=False,
        transcript_segment_count=0,
        metric_source_note=PLATFORM_METRIC_NOTES["facebook"],
        transcript_source_note=FACEBOOK_TRANSCRIPT_UNAVAILABLE_NOTE,
        missing_fields=[
            "transcript",
            "views",
            "reactions",
            "comments",
            "shares",
            "creator",
            "follower_count",
            "hashtags",
            "upload_date",
            "duration_seconds",
        ],
    )


def _safe_error_message(message: str) -> str:
    clean_message = message.strip().splitlines()[0] if message.strip() else ""
    return (clean_message or "Facebook extraction failed.")[:200]
