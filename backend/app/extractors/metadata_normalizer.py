import re
from datetime import UTC, datetime
from typing import Any

from app.models.video import Platform, VideoMetadata


HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w]+)")

PLATFORM_METRIC_NOTES: dict[str, str] = {
    "youtube": (
        "YouTube public metrics are extracted when available. Counts can differ "
        "from the live UI because of rounding, caching, timezone differences, "
        "or update delay. Missing fields are unavailable and not estimated."
    ),
    "instagram": (
        "Instagram public metrics are extracted when available. Public extraction "
        "may exclude Facebook cross-posted reactions, comments, shares, views, "
        "or profile metrics. Missing fields are unavailable and not estimated."
    ),
    "facebook": (
        "Facebook public metrics are extracted when available. Some fields such "
        "as reactions, shares, comments, follower count, or views may be "
        "unavailable from public extraction and are not estimated."
    ),
}


def normalize_metadata(
    *,
    platform: Platform,
    url: str,
    info: dict[str, Any],
    slot: str | None = None,
    transcript_available: bool = False,
    transcript_segment_count: int = 0,
    transcript_language: str | None = None,
    detected_language: str | None = None,
    language_confidence: float | None = None,
    transcript_source: str | None = None,
    extraction_status: str = "partial",
    error_message: str | None = None,
    metric_source_note: str | None = None,
    transcript_source_note: str | None = None,
) -> VideoMetadata:
    title = _first_text(info, ["title", "fulltitle"])
    description = _first_text(info, ["description", "caption", "summary"])
    caption = _first_text(info, ["caption", "description"])
    creator = _first_text(
        info,
        [
            "uploader",
            "channel",
            "creator",
            "uploader_id",
            "channel_id",
            "webpage_url_basename",
        ],
    )
    creator_handle = _first_text(info, ["uploader_id", "channel_id", "creator_id"])
    views = _first_int(info, ["view_count", "views"])
    likes = _first_int(info, ["like_count", "likes"])
    comments = _first_int(info, ["comment_count", "comments"])
    reactions = _first_int(info, ["reaction_count", "reactions"])
    shares = _share_count(platform=platform, info=info)
    follower_count = _first_int(
        info,
        [
            "channel_follower_count",
            "follower_count",
            "uploader_follower_count",
        ],
    )
    subscriber_count = _first_int(info, ["subscriber_count", "channel_subscriber_count"])
    duration_seconds = _first_int(info, ["duration"]) or _duration_string_to_seconds(
        _first_text(info, ["duration_string"])
    )
    upload_date = _upload_date(info)
    thumbnail_url = _first_text(info, ["thumbnail"])
    media_url = _media_url(info)
    audio_url = _audio_url(info) or media_url
    tags = _string_list(info.get("tags")) + _string_list(info.get("hashtags"))
    hashtags = _hashtags(title, description, caption, tags)
    engagement_rate = _engagement_rate(
        platform=platform,
        views=views,
        likes=likes,
        comments=comments,
        reactions=reactions,
        shares=shares,
    )
    missing_fields = _missing_fields(
        platform=platform,
        transcript_available=transcript_available,
        views=views,
        likes=likes,
        comments=comments,
        reactions=reactions,
        shares=shares,
        creator=creator,
        follower_count=follower_count,
        subscriber_count=subscriber_count,
        hashtags=hashtags,
        upload_date=upload_date,
        duration_seconds=duration_seconds,
    )

    return VideoMetadata(
        slot=slot,  # type: ignore[arg-type]
        platform=platform,
        url=_first_text(info, ["webpage_url", "original_url"]) or url,
        title=title,
        creator=creator,
        creator_handle=creator_handle,
        description=description,
        caption=caption,
        views=views,
        likes=likes,
        comments=comments,
        reactions=reactions,
        shares=shares,
        follower_count=follower_count,
        subscriber_count=subscriber_count,
        hashtags=hashtags,
        upload_date=upload_date,
        duration_seconds=duration_seconds,
        thumbnail_url=thumbnail_url,
        media_url=media_url,
        audio_url=audio_url,
        engagement_rate=engagement_rate,
        missing_fields=missing_fields,
        transcript_available=transcript_available,
        transcript_segment_count=transcript_segment_count,
        transcript_language=transcript_language,
        detected_language=detected_language,
        language_confidence=language_confidence,
        transcript_source=transcript_source,
        extraction_status=extraction_status,  # type: ignore[arg-type]
        error_message=error_message,
        metric_source_note=metric_source_note or PLATFORM_METRIC_NOTES[platform],
        transcript_source_note=transcript_source_note,
    )


def extract_best_media_url(info: dict[str, Any]) -> str | None:
    return _media_url(info) or _audio_url(info)


def extract_best_audio_url(info: dict[str, Any]) -> str | None:
    return _audio_url(info) or _media_url(info)


def _first_text(info: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = info.get(key)

        if isinstance(value, str) and value.strip():
            clean_value = value.strip()

            if key == "webpage_url_basename" and len(clean_value) < 3:
                continue

            return clean_value

    return None


def _first_int(info: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        value = _int_value(info.get(key))

        if value is not None:
            return value

    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        clean_value = value.strip().replace(",", "")

        if clean_value.isdigit():
            return int(clean_value)

    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _hashtags(
    title: str | None,
    description: str | None,
    caption: str | None,
    tags: list[str],
) -> list[str]:
    collected: list[str] = []

    for text in (title, description, caption):
        if text:
            collected.extend(HASHTAG_PATTERN.findall(text))

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


def _upload_date(info: dict[str, Any]) -> str | None:
    for key in ("upload_date", "timestamp", "release_timestamp", "modified_timestamp"):
        parsed = _date_value(info.get(key))

        if parsed is not None:
            return parsed

    return None


def _date_value(value: Any) -> str | None:
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


def _duration_string_to_seconds(value: str | None) -> int | None:
    if value is None:
        return None

    parts = value.strip().split(":")

    if not parts or not all(part.isdigit() for part in parts):
        return None

    seconds = 0

    for part in parts:
        seconds = seconds * 60 + int(part)

    return seconds


def _share_count(platform: Platform, info: dict[str, Any]) -> int | None:
    share_count = _first_int(info, ["share_count", "shares"])

    if share_count is not None:
        return share_count

    if platform == "facebook":
        return _first_int(info, ["repost_count"])

    return None


def _media_url(info: dict[str, Any]) -> str | None:
    direct_url = _first_text(info, ["url"])

    if direct_url:
        return direct_url

    formats = info.get("formats")

    if not isinstance(formats, list):
        return None

    usable_formats = [
        item for item in formats if isinstance(item, dict) and _format_url(item)
    ]

    if not usable_formats:
        return None

    selected = max(usable_formats, key=_format_quality)
    return _format_url(selected)


def _audio_url(info: dict[str, Any]) -> str | None:
    formats = info.get("formats")

    if not isinstance(formats, list):
        return None

    usable_formats = [
        item
        for item in formats
        if isinstance(item, dict)
        and _format_url(item)
        and _has_audio(item)
    ]

    audio_only = [item for item in usable_formats if _is_audio_only(item)]
    selected = (
        max(audio_only, key=_format_quality)
        if audio_only
        else max(usable_formats, key=_format_quality)
        if usable_formats
        else None
    )

    return _format_url(selected) if selected else None


def _format_url(format_info: dict[str, Any]) -> str | None:
    url = format_info.get("url")
    return url.strip() if isinstance(url, str) and url.strip() else None


def _has_audio(format_info: dict[str, Any]) -> bool:
    acodec = format_info.get("acodec")
    return isinstance(acodec, str) and acodec != "none"


def _is_audio_only(format_info: dict[str, Any]) -> bool:
    vcodec = format_info.get("vcodec")
    return isinstance(vcodec, str) and vcodec == "none"


def _format_quality(format_info: dict[str, Any]) -> float:
    for key in ("height", "abr", "tbr", "filesize", "filesize_approx"):
        value = format_info.get(key)

        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)

    return 0.0


def _engagement_rate(
    *,
    platform: Platform,
    views: int | None,
    likes: int | None,
    comments: int | None,
    reactions: int | None,
    shares: int | None,
) -> float | None:
    if views is None or views <= 0:
        return None

    if platform == "facebook":
        interactions = _sum_available([reactions, comments, shares])
    else:
        interactions = _sum_available([likes, comments])

    if interactions is None:
        return None

    return round((interactions / views) * 100, 2)


def _sum_available(values: list[int | None]) -> int | None:
    available_values = [value for value in values if value is not None]

    if not available_values:
        return None

    return sum(available_values)


def _missing_fields(
    *,
    platform: Platform,
    transcript_available: bool,
    views: int | None,
    likes: int | None,
    comments: int | None,
    reactions: int | None,
    shares: int | None,
    creator: str | None,
    follower_count: int | None,
    subscriber_count: int | None,
    hashtags: list[str],
    upload_date: str | None,
    duration_seconds: int | None,
) -> list[str]:
    missing: list[str] = []

    if not transcript_available:
        missing.append("transcript")

    if views is None:
        missing.append("views")

    if platform == "facebook":
        if reactions is None:
            missing.append("reactions")
        if shares is None:
            missing.append("shares")
    elif likes is None:
        missing.append("likes")

    if comments is None:
        missing.append("comments")

    if creator is None:
        missing.append("creator")

    if follower_count is None and subscriber_count is None:
        missing.append("follower_count")

    if not hashtags:
        missing.append("hashtags")

    if upload_date is None:
        missing.append("upload_date")

    if duration_seconds is None:
        missing.append("duration_seconds")

    return missing
