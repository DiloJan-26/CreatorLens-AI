from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi import HTTPException, status

from app.extractors.instagram_extractor import extract_instagram_video
from app.extractors.youtube_extractor import extract_youtube_video
from app.models.project import (
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
from app.services.storage_service import (
    create_project_record,
    get_project_detail_record,
    get_project_record,
    get_rag_chunks,
    get_transcript_preview,
    get_video_by_project_platform,
    list_project_records,
    replace_rag_chunks,
    replace_transcript_segments,
    update_project_status,
    upsert_video_metadata,
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
    youtube_url = payload.youtube_url.strip()
    instagram_url = payload.instagram_url.strip()

    if not is_valid_youtube_url(youtube_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid YouTube Shorts, YouTube watch, or youtu.be URL.",
        )

    if not is_valid_instagram_url(instagram_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid Instagram Reel or post URL.",
        )

    project_id = str(uuid4())
    create_project_record(
        project_id=project_id,
        youtube_url=youtube_url,
        instagram_url=instagram_url,
        status="created",
    )

    return ProjectCreateResponse(
        project_id=project_id,
        status="created",
        message="Project created successfully. YouTube and Instagram extraction can now run.",
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


def get_project_transcript_preview(
    project_id: str,
    platform: str,
    limit: int = 10,
) -> TranscriptPreviewResponse:
    if platform not in {"youtube", "instagram"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Platform must be youtube or instagram.",
        )

    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    preview = get_transcript_preview(
        project_id=project_id,
        platform=platform,
        limit=limit,
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

    platform_statuses = [
        _extract_and_store_platform(
            project_id=project_id,
            platform="youtube",
            url=str(record["youtube_url"]),
            extractor=extract_youtube_video,
        ),
        _extract_and_store_platform(
            project_id=project_id,
            platform="instagram",
            url=str(record["instagram_url"]),
            extractor=extract_instagram_video,
        ),
    ]

    update_project_status(
        project_id,
        _project_status_from_video_statuses(platform_statuses),
    )

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
    platform: str,
    url: str,
    extractor,
) -> str:
    existing_video = get_video_by_project_platform(project_id, platform)

    if _is_successful_video(existing_video):
        return str(existing_video["extraction_status"])

    try:
        extraction_result = extractor(url)
    except Exception:
        extraction_result = VideoExtractionResult(
            metadata=_failed_video_metadata(
                platform=platform,
                url=url,
                message=f"{_platform_display_name(platform)} extraction failed.",
            ),
            transcript_segments=[],
        )

    try:
        video_record = upsert_video_metadata(
            project_id=project_id,
            metadata=extraction_result.metadata,
        )
        replace_transcript_segments(
            project_id=project_id,
            platform=platform,
            video_id=str(video_record["id"]),
            segments=extraction_result.transcript_segments,
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


def _chunk_build_response(
    project_id: str,
    chunks: list[RagChunk],
) -> ChunkBuildResponse:
    return ChunkBuildResponse(
        project_id=project_id,
        total_chunks=len(chunks),
        youtube_chunks=sum(1 for chunk in chunks if chunk.platform == "youtube"),
        instagram_chunks=sum(1 for chunk in chunks if chunk.platform == "instagram"),
        chunks=chunks,
    )


def _failed_video_metadata(platform: str, url: str, message: str) -> VideoMetadata:
    return VideoMetadata(
        platform=platform,
        url=url,
        extraction_status="failed",
        error_message=_safe_error_message(message),
        transcript_available=False,
        transcript_segment_count=0,
    )


def _safe_error_message(message: str) -> str:
    clean_message = message.strip().splitlines()[0] if message.strip() else ""
    return (clean_message or "Extraction failed.")[:200]


def _platform_display_name(platform: str) -> str:
    if platform == "youtube":
        return "YouTube"

    if platform == "instagram":
        return "Instagram"

    return "Platform"


def list_projects(limit: int = 20) -> ProjectListResponse:
    records = list_project_records(limit=limit)
    return ProjectListResponse(
        projects=[ProjectRecord(**record) for record in records],
    )
