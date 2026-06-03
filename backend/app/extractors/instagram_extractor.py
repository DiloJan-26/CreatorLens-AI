import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from app.extractors.metadata_normalizer import normalize_metadata
from app.models.video import VideoExtractionResult, VideoMetadata
from app.services.transcription_service import transcribe_instagram_audio_url


INSTAGRAM_PLATFORM = "instagram"
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")
INSTAGRAM_METRIC_SOURCE_NOTE = (
    "Instagram metrics are extracted from public Instagram metadata. "
    "Cross-posted Facebook reactions/comments shown in the browser UI may not "
    "be included."
)
INSTAGRAM_TRANSCRIPT_AVAILABLE_NOTE = (
    "Transcript generated from Instagram audio using Deepgram when a public "
    "audio URL is available."
)
INSTAGRAM_TRANSCRIPT_UNAVAILABLE_NOTE = (
    "Instagram audio transcription was unavailable or failed; metadata was "
    "preserved."
)


def is_instagram_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if parsed.scheme not in {"http", "https"}:
        return False

    if host not in {"instagram.com", "www.instagram.com"}:
        return False

    return len(path_parts) >= 2 and path_parts[0] in {"reel", "p"}


def extract_instagram_shortcode(url: str) -> str:
    parsed = urlparse(url.strip())
    path_parts = [part for part in parsed.path.split("/") if part]

    if not is_instagram_url(url) or len(path_parts) < 2:
        raise ValueError("Enter a valid Instagram Reel or post URL.")

    shortcode = path_parts[1].strip()

    if not shortcode:
        raise ValueError("Could not find an Instagram shortcode in the URL.")

    return shortcode


def normalize_instagram_upload_date(value: object) -> str | None:
    if isinstance(value, str):
        clean_value = value.strip()

        if len(clean_value) == 10 and clean_value[4] == "-" and clean_value[7] == "-":
            return clean_value

        if len(clean_value) == 8 and clean_value.isdigit():
            return f"{clean_value[:4]}-{clean_value[4:6]}-{clean_value[6:]}"

        try:
            return datetime.fromisoformat(
                clean_value.replace("Z", "+00:00"),
            ).date().isoformat()
        except ValueError:
            return None

    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), UTC).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return None

    return None


def safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value) if value.is_integer() else None

    if isinstance(value, str):
        clean_value = value.strip().replace(",", "")

        if clean_value.isdigit():
            return int(clean_value)

    return None


def extract_instagram_hashtags(*texts: str | None) -> list[str]:
    seen: set[str] = set()
    hashtags: list[str] = []

    for text in texts:
        if not text:
            continue

        for raw_tag in HASHTAG_PATTERN.findall(text):
            tag = raw_tag.strip().lstrip("#").lower()

            if not tag or tag in seen:
                continue

            seen.add(tag)
            hashtags.append(tag)

    return hashtags


def fetch_instagram_info(url: str) -> dict[str, Any]:
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
            f"Instagram metadata extraction failed: {_safe_error_message(str(exc))}"
        ) from None

    if not isinstance(info, dict):
        raise ValueError("Instagram metadata extraction returned no usable data.")

    return info


def extract_best_instagram_audio_url(info: dict[str, Any]) -> str | None:
    formats = info.get("formats")

    if isinstance(formats, list):
        usable_formats = [
            item for item in formats if isinstance(item, dict) and _format_url(item)
        ]
    else:
        usable_formats = []

    audio_only_formats = [
        item for item in usable_formats if _has_audio(item) and _is_audio_only(item)
    ]
    audio_formats = [item for item in usable_formats if _has_audio(item)]

    selected_format = _best_format(audio_only_formats) or _best_format(audio_formats)

    if selected_format:
        return _format_url(selected_format)

    direct_url = info.get("url")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url.strip()

    return None


def normalize_instagram_metadata(
    url: str,
    info: dict[str, Any],
    transcript_segment_count: int = 0,
    transcript_available: bool = False,
    error_message: str | None = None,
) -> VideoMetadata:
    extraction_status = "ready" if transcript_available else "partial"
    safe_message = _safe_error_message(error_message or "") if error_message else None

    if extraction_status == "partial" and safe_message is None:
        safe_message = "Instagram transcript not extracted yet."

    return normalize_metadata(
        platform=INSTAGRAM_PLATFORM,
        url=url,
        info=info,
        transcript_available=transcript_available,
        transcript_segment_count=transcript_segment_count,
        extraction_status=extraction_status,
        error_message=safe_message,
        metric_source_note=INSTAGRAM_METRIC_SOURCE_NOTE,
        transcript_source_note=(
            INSTAGRAM_TRANSCRIPT_AVAILABLE_NOTE
            if transcript_available
            else INSTAGRAM_TRANSCRIPT_UNAVAILABLE_NOTE
        ),
    )


def extract_instagram_metadata_only(url: str) -> tuple[VideoMetadata, str | None]:
    try:
        extract_instagram_shortcode(url)
        info = fetch_instagram_info(url)
        audio_url = extract_best_instagram_audio_url(info)
        metadata = normalize_instagram_metadata(
            url=url,
            info=info,
            transcript_available=False,
            transcript_segment_count=0,
        )
        return metadata, audio_url
    except Exception as exc:
        failed_result = build_failed_instagram_result(url, _safe_error_message(str(exc)))
        return failed_result.metadata, None


def extract_instagram_video(url: str) -> VideoExtractionResult:
    metadata, audio_url = extract_instagram_metadata_only(url)

    if metadata.extraction_status == "failed":
        return VideoExtractionResult(metadata=metadata, transcript_segments=[])

    transcript_segments = transcribe_instagram_audio_url(audio_url)

    if transcript_segments:
        metadata.transcript_available = True
        metadata.transcript_segment_count = len(transcript_segments)
        metadata.extraction_status = "ready"
        metadata.error_message = None
        metadata.transcript_source_note = INSTAGRAM_TRANSCRIPT_AVAILABLE_NOTE
    else:
        metadata.transcript_available = False
        metadata.transcript_segment_count = 0
        metadata.extraction_status = "partial"
        metadata.error_message = (
            "Instagram metadata extracted, but transcript was unavailable from "
            "audio transcription."
        )
        metadata.transcript_source_note = INSTAGRAM_TRANSCRIPT_UNAVAILABLE_NOTE

    return VideoExtractionResult(
        metadata=metadata,
        transcript_segments=transcript_segments,
    )


def inspect_instagram_metadata(url: str) -> dict[str, Any]:
    info = fetch_instagram_info(url)
    metadata = normalize_instagram_metadata(url, info)

    return {
        "metadata": metadata.model_dump(),
        "has_audio_url": extract_best_instagram_audio_url(info) is not None,
        "raw_keys": sorted(str(key) for key in info.keys()),
    }


def build_failed_instagram_result(url: str, message: str) -> VideoExtractionResult:
    return VideoExtractionResult(
        metadata=VideoMetadata(
            platform=INSTAGRAM_PLATFORM,
            url=url,
            extraction_status="failed",
            error_message=_safe_error_message(message),
            transcript_available=False,
            transcript_segment_count=0,
            metric_source_note=INSTAGRAM_METRIC_SOURCE_NOTE,
            transcript_source_note=INSTAGRAM_TRANSCRIPT_UNAVAILABLE_NOTE,
        ),
        transcript_segments=[],
    )


def _safe_error_message(message: str) -> str:
    clean_message = message.strip().splitlines()[0] if message.strip() else ""
    return (clean_message or "Instagram extraction failed.")[:200]


def _format_url(format_info: dict[str, Any]) -> str | None:
    url = format_info.get("url")
    return url.strip() if isinstance(url, str) and url.strip() else None


def _has_audio(format_info: dict[str, Any]) -> bool:
    acodec = format_info.get("acodec")
    return isinstance(acodec, str) and acodec != "none"


def _is_audio_only(format_info: dict[str, Any]) -> bool:
    vcodec = format_info.get("vcodec")
    return isinstance(vcodec, str) and vcodec == "none"


def _best_format(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not formats:
        return None

    return max(formats, key=_format_quality)


def _format_quality(format_info: dict[str, Any]) -> float:
    for key in ("abr", "tbr", "filesize", "filesize_approx"):
        value = format_info.get(key)

        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)

    return 0.0


def _as_optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
