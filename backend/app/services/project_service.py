from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi import HTTPException, status

from app.extractors.youtube_extractor import extract_youtube_video
from app.models.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRecord,
)
from app.services.storage_service import (
    create_project_record,
    get_project_detail_record,
    get_project_record,
    list_project_records,
    replace_transcript_segments,
    update_project_status,
    upsert_video_metadata,
)


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
        message="Project created successfully. Extraction pipeline will run in the next backend milestone.",
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


def extract_project_youtube(project_id: str) -> ProjectDetailResponse:
    record = get_project_record(project_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    try:
        update_project_status(project_id, "extracting")
        extraction_result = extract_youtube_video(str(record["youtube_url"]))
        video_record = upsert_video_metadata(
            project_id=project_id,
            metadata=extraction_result.metadata,
        )
        replace_transcript_segments(
            project_id=project_id,
            platform="youtube",
            video_id=str(video_record["id"]),
            segments=extraction_result.transcript_segments,
        )

        if extraction_result.metadata.extraction_status == "ready":
            update_project_status(project_id, "ready")
        elif extraction_result.metadata.extraction_status == "failed":
            update_project_status(project_id, "failed")

        return get_project_detail(project_id)
    except HTTPException:
        raise
    except Exception:
        update_project_status(project_id, "failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not extract YouTube data for this project.",
        ) from None


def list_projects(limit: int = 20) -> ProjectListResponse:
    records = list_project_records(limit=limit)
    return ProjectListResponse(
        projects=[ProjectRecord(**record) for record in records],
    )
