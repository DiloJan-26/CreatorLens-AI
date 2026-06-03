import hashlib
import uuid
from typing import Any

from app.models.rag import RagChunk, RagPlatform, RagSourceType
from app.services.metric_source_service import get_metric_summary
from app.services.storage_service import (
    get_project_detail_record,
    get_transcript_segments,
)


TRANSCRIPT_MIN_CHARS = 500
TRANSCRIPT_MAX_CHARS = 900


def build_project_chunks(project_id: str) -> list[RagChunk]:
    project = get_project_detail_record(project_id)

    if project is None:
        raise ValueError("Project not found.")

    chunks: list[RagChunk] = []

    for metadata in project.get("content_items", []):
        if not isinstance(metadata, dict):
            continue

        platform = metadata.get("platform")
        slot = metadata.get("slot")

        if platform not in {"youtube", "instagram", "facebook"}:
            continue

        transcript_segments = get_transcript_segments(
            project_id=project_id,
            platform=platform,
            slot=slot,
        )
        chunks.extend(
            _build_platform_chunks(
                project_id=project_id,
                slot=slot,
                platform=platform,
                metadata=metadata,
                transcript_segments=transcript_segments,
            )
        )

    return chunks


def _build_platform_chunks(
    project_id: str,
    slot: str | None,
    platform: RagPlatform,
    metadata: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    chunk_index = 0
    content_id = (
        _optional_text(metadata.get("content_id"))
        or _optional_text(metadata.get("id"))
    )

    chunks.append(
        _make_chunk(
            project_id=project_id,
            content_id=content_id,
            slot=slot,
            platform=platform,
            source_type="metadata",
            chunk_index=chunk_index,
            title=_optional_text(metadata.get("title")),
            creator=_optional_text(metadata.get("creator")),
            text=_metadata_text(project_id, platform, metadata),
            citation_label=_citation_label(slot, platform, "metadata", None, None),
        )
    )
    chunk_index += 1

    description = _optional_text(metadata.get("description"))

    if description:
        description_label = _description_label(platform)
        chunks.append(
            _make_chunk(
                project_id=project_id,
                content_id=content_id,
                slot=slot,
                platform=platform,
                source_type="description",
                chunk_index=chunk_index,
                title=_optional_text(metadata.get("title")),
                creator=_optional_text(metadata.get("creator")),
                text=_description_text(platform, metadata, description),
                citation_label=_citation_label(
                    slot,
                    platform,
                    description_label,
                    None,
                    None,
                ),
            )
        )
        chunk_index += 1

    clean_segments = _clean_transcript_segments(transcript_segments)
    hook_segments = _hook_segments(clean_segments)

    if hook_segments:
        start_time, end_time = _segment_time_range(hook_segments)
        chunks.append(
            _make_chunk(
                project_id=project_id,
                content_id=content_id,
                slot=slot,
                platform=platform,
                source_type="hook",
                chunk_index=chunk_index,
                start_time=start_time,
                end_time=end_time,
                title=_optional_text(metadata.get("title")),
                creator=_optional_text(metadata.get("creator")),
                text=_segments_text(hook_segments),
                citation_label=_citation_label(slot, platform, "hook", start_time, end_time),
            )
        )
        chunk_index += 1

    for transcript_chunk_segments in _transcript_chunk_segments(clean_segments):
        start_time, end_time = _segment_time_range(transcript_chunk_segments)
        chunks.append(
            _make_chunk(
                project_id=project_id,
                content_id=content_id,
                slot=slot,
                platform=platform,
                source_type="transcript",
                chunk_index=chunk_index,
                start_time=start_time,
                end_time=end_time,
                title=_optional_text(metadata.get("title")),
                creator=_optional_text(metadata.get("creator")),
                text=_segments_text(transcript_chunk_segments),
                citation_label=_citation_label(
                    slot,
                    platform,
                    "transcript",
                    start_time,
                    end_time,
                ),
            )
        )
        chunk_index += 1

    return chunks


def _metadata_text(
    project_id: str,
    platform: RagPlatform,
    metadata: dict[str, Any],
) -> str:
    lines = [
        f"Platform: {_platform_label(platform)}",
        f"Content slot: {_slot_label(_optional_text(metadata.get('slot')))}",
        f"Title: {_display_value(metadata.get('title'))}",
        f"Creator: {_display_value(metadata.get('creator'))}",
        "Confirmed public metrics:",
        f"Views: {_display_number(metadata.get('views'))}",
        f"Likes: {_display_number(metadata.get('likes'))}",
        f"Reactions: {_display_number(metadata.get('reactions'))}",
        f"Comments: {_display_number(metadata.get('comments'))}",
        f"Shares: {_display_number(metadata.get('shares'))}",
        f"Engagement rate: {_display_percent(metadata.get('engagement_rate'))}",
        f"Follower count: {_display_number(metadata.get('follower_count'))}",
        f"Subscriber count: {_display_number(metadata.get('subscriber_count'))}",
        f"Duration seconds: {_display_number(metadata.get('duration_seconds'))}",
        f"Upload date: {_display_value(metadata.get('upload_date'))}",
        f"Hashtags: {_display_hashtags(metadata.get('hashtags'))}",
        f"Available fields: {_display_field_list(_available_fields(metadata))}",
        f"Missing fields: {_display_field_list(metadata.get('missing_fields'))}",
        f"Metric source note: {_display_value(metadata.get('metric_source_note'))}",
        f"Transcript source note: {_display_value(metadata.get('transcript_source_note'))}",
    ]
    metric_source_text = _metric_source_text(project_id, platform)

    if metric_source_text:
        lines.append(metric_source_text)

    return "\n".join(lines)


def _description_text(
    platform: RagPlatform,
    metadata: dict[str, Any],
    description: str,
) -> str:
    description_name = "Caption" if platform == "instagram" else "Description"

    return "\n".join(
        [
            f"Content slot: {_slot_label(_optional_text(metadata.get('slot')))}",
            f"Platform: {_platform_label(platform)}",
            f"Title: {_display_value(metadata.get('title'))}",
            f"{description_name}: {description}",
            f"Hashtags: {_display_hashtags(metadata.get('hashtags'))}",
        ]
    )


def _hook_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timed_segments = [
        segment
        for segment in segments
        if (start_time := _as_float(segment.get("start_time"))) is not None
        and start_time <= 5.0
    ]

    if timed_segments:
        return timed_segments

    return segments[:2]


def _transcript_chunk_segments(
    segments: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    if not segments:
        return []

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for segment in segments:
        projected_length = _segments_length(current) + len(str(segment["text"])) + 1

        if (
            current
            and projected_length > TRANSCRIPT_MAX_CHARS
            and _segments_length(current) >= TRANSCRIPT_MIN_CHARS
        ):
            chunks.append(current)
            current = current[-1:] if len(current) > 1 else []

        current.append(segment)

    if current:
        chunks.append(current)

    return chunks


def _make_chunk(
    project_id: str,
    content_id: str | None,
    slot: str | None,
    platform: RagPlatform,
    source_type: RagSourceType,
    chunk_index: int,
    text: str,
    citation_label: str,
    start_time: float | None = None,
    end_time: float | None = None,
    title: str | None = None,
    creator: str | None = None,
) -> RagChunk:
    content_hash = _content_hash(project_id, slot, platform, source_type, text)
    chunk_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"creatorlens:{project_id}:{slot}:{platform}:{source_type}:{chunk_index}:{content_hash}",
        )
    )

    return RagChunk(
        chunk_id=chunk_id,
        project_id=project_id,
        content_id=content_id,
        slot=slot,  # type: ignore[arg-type]
        platform=platform,
        source_type=source_type,
        chunk_index=chunk_index,
        start_time=start_time,
        end_time=end_time,
        title=title,
        creator=creator,
        text=text,
        content_hash=content_hash,
        citation_label=citation_label,
        qdrant_point_id=None,
    )


def _content_hash(
    project_id: str,
    slot: str | None,
    platform: RagPlatform,
    source_type: RagSourceType,
    text: str,
) -> str:
    raw_content = f"{project_id}|{slot}|{platform}|{source_type}|{text}"
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


def _citation_label(
    slot: str | None,
    platform: RagPlatform,
    source_label: str,
    start_time: float | None,
    end_time: float | None,
) -> str:
    label = f"{_slot_label(slot)} · {_platform_label(platform)} · {source_label}"

    if start_time is None or end_time is None:
        return label

    return f"{label} · {_format_seconds(start_time)}-{_format_seconds(end_time)}"


def _segment_time_range(segments: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    if not segments:
        return None, None

    return _as_float(segments[0].get("start_time")), _as_float(segments[-1].get("end_time"))


def _clean_transcript_segments(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clean_segments: list[dict[str, Any]] = []

    for segment in segments:
        text = _optional_text(segment.get("text"))

        if text is None:
            continue

        clean_segments.append(
            {
                "segment_index": segment.get("segment_index"),
                "start_time": _as_float(segment.get("start_time")),
                "end_time": _as_float(segment.get("end_time")),
                "text": text,
            }
        )

    return clean_segments


def _segments_text(segments: list[dict[str, Any]]) -> str:
    return " ".join(str(segment["text"]).strip() for segment in segments).strip()


def _segments_length(segments: list[dict[str, Any]]) -> int:
    return len(_segments_text(segments))


def _metric_source_text(project_id: str, platform: RagPlatform) -> str:
    try:
        summary = get_metric_summary(project_id)
    except Exception:
        return ""

    source_record = next(
        (
            record
            for record in summary.records
            if record.source_platform == platform and record.metric_scope == "native"
        ),
        None,
    )
    platform_status = _platform_status(summary, platform)
    lines = [
        "Metric Source Resolver:",
        f"{_platform_label(platform)} native completeness status: {platform_status}",
    ]

    if source_record is not None:
        lines.extend(
            [
                f"Metric source method: {source_record.source_method}",
                f"Metric source confidence: {source_record.confidence}",
                f"Verified followers: {_display_number(source_record.followers)}",
                f"Unavailable native fields: {_missing_record_fields(source_record)}",
            ]
        )

    if platform == "instagram":
        lines.extend(
            [
                f"Facebook cross-post status: {summary.facebook_crosspost_status}",
                f"Combined Meta engagement rate: {_display_percent(summary.combined_meta_engagement_rate)}",
                f"Combined Meta views: {_display_number(summary.combined_meta_views)}",
                f"Combined Meta interactions: {_display_number(summary.combined_meta_interactions)}",
            ]
        )

    lines.append("Rule: unavailable metrics must not be estimated.")

    return "\n".join(lines)


def _missing_record_fields(record: Any) -> str:
    missing_fields = [
        field_name
        for field_name in (
            "views",
            "likes",
            "reactions",
            "comments",
            "shares",
            "followers",
            "engagement_rate",
        )
        if getattr(record, field_name, None) is None
    ]

    return ", ".join(missing_fields) if missing_fields else "None"


def _platform_status(summary: Any, platform: RagPlatform) -> str:
    if platform == "youtube":
        return str(summary.youtube_status)

    if platform == "instagram":
        return str(summary.instagram_native_status)

    matching_record = next(
        (
            record
            for record in summary.records
            if record.source_platform == platform and record.metric_scope == "native"
        ),
        None,
    )

    if matching_record is None:
        return "unavailable"

    missing_fields = _missing_record_fields(matching_record)
    return "complete" if missing_fields == "None" else "partial"


def _available_fields(metadata: dict[str, Any]) -> list[str]:
    field_values = {
        "transcript": bool(metadata.get("transcript_available")),
        "views": metadata.get("views") is not None,
        "likes": metadata.get("likes") is not None,
        "reactions": metadata.get("reactions") is not None,
        "comments": metadata.get("comments") is not None,
        "shares": metadata.get("shares") is not None,
        "creator": _optional_text(metadata.get("creator")) is not None,
        "follower_count": metadata.get("follower_count") is not None,
        "subscriber_count": metadata.get("subscriber_count") is not None,
        "hashtags": bool(metadata.get("hashtags")),
        "upload_date": metadata.get("upload_date") is not None,
        "duration_seconds": metadata.get("duration_seconds") is not None,
        "engagement_rate": metadata.get("engagement_rate") is not None,
    }

    return [
        field_name
        for field_name, is_available in field_values.items()
        if is_available
    ]


def _display_field_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "Unavailable"

    fields = [
        str(item).replace("_", " ")
        for item in value
        if isinstance(item, str) and item.strip()
    ]

    return ", ".join(fields) if fields else "Unavailable"


def _platform_label(platform: RagPlatform) -> str:
    if platform == "youtube":
        return "YouTube"

    if platform == "instagram":
        return "Instagram"

    if platform == "facebook":
        return "Facebook"

    return platform


def _description_label(platform: RagPlatform) -> str:
    return "caption" if platform == "instagram" else "description"


def _slot_label(slot: str | None) -> str:
    if slot == "content_1":
        return "Content 1"

    if slot == "content_2":
        return "Content 2"

    return "Content"


def _display_value(value: Any) -> str:
    text = _optional_text(value)
    return text if text is not None else "Unavailable"


def _display_number(value: Any) -> str:
    if isinstance(value, bool):
        return "Unavailable"

    if isinstance(value, int):
        return f"{value:,}"

    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"

    return "Unavailable"


def _display_percent(value: Any) -> str:
    if isinstance(value, bool):
        return "Unavailable"

    if isinstance(value, int | float):
        return f"{float(value):.2f}%"

    return "Unavailable"


def _display_hashtags(value: Any) -> str:
    if not isinstance(value, list):
        return "Unavailable"

    tags = [
        f"#{tag.strip().lstrip('#')}"
        for tag in value
        if isinstance(tag, str) and tag.strip()
    ]

    return ", ".join(tags) if tags else "Unavailable"


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _format_seconds(value: float) -> str:
    return f"{value:.2f}s"
