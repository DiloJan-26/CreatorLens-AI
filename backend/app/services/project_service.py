from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi import HTTPException, status

from app.extractors.facebook_extractor import extract_facebook_content
from app.extractors.instagram_extractor import extract_instagram_video
from app.extractors.youtube_extractor import extract_youtube_video
from app.models.project import (
    MetadataAvailabilityItem,
    MetadataAvailabilityResponse,
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRecord,
)
from app.models.rag import ChunkBuildResponse, RagChunk
from app.models.video import (
    TranscriptPreviewResponse,
    VideoExtractionResult,
    VideoMetadata,
)
from app.rag.chunk_builder import build_project_chunks
from app.services.metric_source_service import ensure_public_metric_records
from app.services.storage_service import (
    create_project_record,
    get_project_detail_record,
    get_project_record,
    get_rag_chunks,
    get_transcript_preview,
    get_video_by_project_slot,
    list_video_records,
    list_project_records,
    replace_rag_chunks,
    replace_transcript_segments,
    update_project_status,
    upsert_video_metadata,
)
from app.services.platform_detection_service import (
    UnsupportedPlatformUrlError,
    detect_platform,
)


SUCCESSFUL_VIDEO_STATUSES = {"ready", "partial"}


def is_valid_youtube_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path

    if parsed.scheme not in {"http", "https"}:
        return False

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return path.startswith("/shorts/") or (
            path == "/watch" and bool(parse_qs(parsed.query).get("v"))
        )

    if host == "youtu.be":
        return bool(path.strip("/"))

    return False


def is_valid_instagram_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path

    if parsed.scheme not in {"http", "https"}:
        return False

    if host not in {"instagram.com", "www.instagram.com"}:
        return False

    return path.startswith("/reel/") or path.startswith("/p/")


def create_project(payload: ProjectCreateRequest) -> ProjectCreateResponse:
    content_1_url = str(payload.content_1_url or "").strip()
    content_2_url = str(payload.content_2_url or "").strip()

    try:
        content_1_platform = detect_platform(content_1_url)
        content_2_platform = detect_platform(content_2_url)
    except UnsupportedPlatformUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    youtube_url = _legacy_platform_url(
        content_1_url=content_1_url,
        content_1_platform=content_1_platform,
        content_2_url=content_2_url,
        content_2_platform=content_2_platform,
        platform="youtube",
    )
    instagram_url = _legacy_platform_url(
        content_1_url=content_1_url,
        content_1_platform=content_1_platform,
        content_2_url=content_2_url,
        content_2_platform=content_2_platform,
        platform="instagram",
    )

    project_id = str(uuid4())
    create_project_record(
        project_id=project_id,
        youtube_url=youtube_url,
        instagram_url=instagram_url,
        content_1_url=content_1_url,
        content_2_url=content_2_url,
        content_1_platform=content_1_platform,
        content_2_platform=content_2_platform,
        status="created",
    )

    return ProjectCreateResponse(
        project_id=project_id,
        status="created",
        message="Project created successfully. Content extraction can now run.",
    )


def get_project(project_id: str) -> ProjectRecord:
    record = get_project_record(project_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return ProjectRecord(**record)


def get_project_detail(project_id: str) -> ProjectDetailResponse:
    record = get_project_detail_record(project_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return ProjectDetailResponse(**record)


def get_metadata_availability(project_id: str) -> MetadataAvailabilityResponse:
    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    items = [
        _metadata_availability_item(record)
        for record in list_video_records(project_id)
    ]

    return MetadataAvailabilityResponse(project_id=project_id, items=items)


def get_project_transcript_preview(
    project_id: str,
    platform: str | None = None,
    limit: int = 10,
    slot: str | None = None,
) -> TranscriptPreviewResponse:
    if platform is not None and platform not in {"youtube", "instagram", "facebook"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Platform must be youtube, instagram, or facebook.",
        )

    if platform is None and slot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a content slot or platform.",
        )

    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    preview = get_transcript_preview(
        project_id=project_id,
        platform=platform or "youtube",
        limit=limit,
        slot=slot,
    )

    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript data not found for this platform.",
        )

    return TranscriptPreviewResponse(**preview)


def extract_project_videos(project_id: str) -> ProjectDetailResponse:
    record = get_project_record(project_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    update_project_status(project_id, "extracting")

    platform_statuses = []

    for slot in ("content_1", "content_2"):
        platform_statuses.append(
            _extract_and_store_platform(
                project_id=project_id,
                slot=slot,
                platform=str(record[f"{slot}_platform"]),
                url=str(record[f"{slot}_url"]),
            )
        )

    update_project_status(
        project_id,
        _project_status_from_video_statuses(platform_statuses),
    )
    _seed_metric_sources(project_id)

    return get_project_detail(project_id)


def extract_project_youtube(project_id: str) -> ProjectDetailResponse:
    return extract_project_videos(project_id)


def build_and_store_project_chunks(project_id: str) -> ChunkBuildResponse:
    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    chunks = build_project_chunks(project_id)
    replace_rag_chunks(project_id=project_id, chunks=chunks)

    return _chunk_build_response(project_id, chunks)


def get_project_chunks(
    project_id: str,
    platform: str | None = None,
) -> ChunkBuildResponse:
    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    try:
        chunk_records = get_rag_chunks(project_id=project_id, platform=platform)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    chunks = [RagChunk(**record) for record in chunk_records]
    return _chunk_build_response(project_id, chunks)


def _extract_and_store_platform(
    project_id: str,
    slot: str,
    platform: str,
    url: str,
) -> str:
    existing_video = get_video_by_project_slot(project_id, slot)

    if _is_successful_video(existing_video):
        return str(existing_video["extraction_status"])

    try:
        extraction_result = _extract_url(
            project_id=project_id,
            slot=slot,
            platform=platform,
            url=url,
        )
    except Exception:
        extraction_result = VideoExtractionResult(
            metadata=_failed_video_metadata(
                slot=slot,
                platform=platform,
                url=url,
                message=f"{_platform_display_name(platform)} extraction failed.",
            ),
            transcript_segments=[],
        )

    try:
        extraction_result.metadata.slot = slot  # type: ignore[assignment]
        video_record = upsert_video_metadata(
            project_id=project_id,
            metadata=extraction_result.metadata,
            slot=slot,
        )
        replace_transcript_segments(
            project_id=project_id,
            platform=platform,
            video_id=str(video_record["id"]),
            segments=extraction_result.transcript_segments,
            slot=slot,
        )
    except Exception:
        return "failed"

    return extraction_result.metadata.extraction_status


def _is_successful_video(record: dict | None) -> bool:
    if record is None:
        return False

    return str(record.get("extraction_status")) in SUCCESSFUL_VIDEO_STATUSES


def _project_status_from_video_statuses(video_statuses: list[str]) -> str:
    if any(video_status in SUCCESSFUL_VIDEO_STATUSES for video_status in video_statuses):
        return "ready"

    return "failed"


def _metadata_availability_item(record: dict) -> MetadataAvailabilityItem:
    field_values = {
        "transcript": bool(record.get("transcript_available")),
        "views": record.get("views") is not None,
        "likes/reactions": (
            record.get("reactions") is not None
            if record.get("platform") == "facebook"
            else record.get("likes") is not None
        ),
        "comments": record.get("comments") is not None,
        "creator": bool(record.get("creator")),
        "follower_count/subscriber_count": (
            record.get("follower_count") is not None
            or record.get("subscriber_count") is not None
        ),
        "hashtags": bool(record.get("hashtags")),
        "upload_date": record.get("upload_date") is not None,
        "duration_seconds": record.get("duration_seconds") is not None,
    }
    available_fields = [
        field_name for field_name, is_available in field_values.items() if is_available
    ]
    missing_fields = [
        field_name
        for field_name, is_available in field_values.items()
        if not is_available
    ]
    completeness_score = round((len(available_fields) / len(field_values)) * 100, 2)

    return MetadataAvailabilityItem(
        slot=str(record.get("slot") or ""),
        platform=record["platform"],
        url=str(record.get("url") or ""),
        available_fields=available_fields,
        missing_fields=missing_fields,
        completeness_score=completeness_score,
        note=(
            "Confirmed public metrics are shown when extracted. Missing fields "
            "are unavailable and not estimated."
        ),
    )


def _chunk_build_response(
    project_id: str,
    chunks: list[RagChunk],
) -> ChunkBuildResponse:
    return ChunkBuildResponse(
        project_id=project_id,
        total_chunks=len(chunks),
        youtube_chunks=sum(1 for chunk in chunks if chunk.platform == "youtube"),
        instagram_chunks=sum(1 for chunk in chunks if chunk.platform == "instagram"),
        facebook_chunks=sum(1 for chunk in chunks if chunk.platform == "facebook"),
        chunks_by_platform=_chunk_counts_by_field(chunks, "platform"),
        chunks_by_slot=_chunk_counts_by_field(chunks, "slot"),
        chunks_by_source_type=_chunk_counts_by_field(chunks, "source_type"),
        content_chunk_counts=_content_chunk_counts(chunks),
        chunks=chunks,
    )


def _chunk_counts_by_field(
    chunks: list[RagChunk],
    field_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for chunk in chunks:
        value = getattr(chunk, field_name, None)

        if value is None:
            continue

        key = str(value)
        counts[key] = counts.get(key, 0) + 1

    return dict(sorted(counts.items()))


def _content_chunk_counts(chunks: list[RagChunk]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str], int] = {}

    for chunk in chunks:
        slot = str(chunk.slot or "content")
        platform = str(chunk.platform)
        key = (slot, platform)
        counts[key] = counts.get(key, 0) + 1

    return [
        {
            "slot": slot,
            "label": _slot_label(slot),
            "platform": platform,
            "chunks": count,
        }
        for (slot, platform), count in sorted(
            counts.items(),
            key=lambda item: (_slot_sort_key(item[0][0]), item[0][1]),
        )
    ]


def _slot_label(slot: str) -> str:
    if slot == "content_1":
        return "Content 1"

    if slot == "content_2":
        return "Content 2"

    return "Content"


def _slot_sort_key(slot: str) -> int:
    if slot == "content_1":
        return 0

    if slot == "content_2":
        return 1

    return 2


def _extract_url(
    *,
    project_id: str,
    slot: str,
    platform: str,
    url: str,
) -> VideoExtractionResult:
    if platform == "youtube":
        return extract_youtube_video(url)

    if platform == "instagram":
        return extract_instagram_video(url)

    if platform == "facebook":
        return extract_facebook_content(url=url, project_id=project_id, slot=slot)

    raise ValueError("Unsupported platform.")


def _failed_video_metadata(
    platform: str,
    url: str,
    message: str,
    slot: str | None = None,
) -> VideoMetadata:
    return VideoMetadata(
        slot=slot,  # type: ignore[arg-type]
        platform=platform,
        url=url,
        extraction_status="failed",
        error_message=_safe_error_message(message),
        transcript_available=False,
        transcript_segment_count=0,
        transcript_source="unavailable",
        transcript_source_note=(
            "Transcript unavailable because audio transcription failed or public media audio could not be extracted."
        ),
    )


def _safe_error_message(message: str) -> str:
    clean_message = message.strip().splitlines()[0] if message.strip() else ""
    return (clean_message or "Extraction failed.")[:200]


def _platform_display_name(platform: str) -> str:
    if platform == "youtube":
        return "YouTube"

    if platform == "instagram":
        return "Instagram"

    if platform == "facebook":
        return "Facebook"

    return "Platform"


def _legacy_platform_url(
    *,
    content_1_url: str,
    content_1_platform: str,
    content_2_url: str,
    content_2_platform: str,
    platform: str,
) -> str:
    if content_1_platform == platform:
        return content_1_url

    if content_2_platform == platform:
        return content_2_url

    return content_1_url if platform == "youtube" else content_2_url


def _seed_metric_sources(project_id: str) -> None:
    try:
        ensure_public_metric_records(project_id)
    except Exception:
        return


def list_projects(limit: int = 20) -> ProjectListResponse:
    records = list_project_records(limit=limit)
    return ProjectListResponse(
        projects=[ProjectRecord(**record) for record in records],
    )
