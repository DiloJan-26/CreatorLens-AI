from fastapi import APIRouter, HTTPException, Query, status

from app.models.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
)
from app.models.rag import (
    ChunkBuildResponse,
    IndexProjectResponse,
    RagChunkListResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from app.models.video import Platform, TranscriptPreviewResponse
from app.rag.indexing_service import (
    ProjectIndexingNotFoundError,
    index_project,
)
from app.rag.retrieval_service import (
    RetrievalProjectNotFoundError,
    RetrievalValidationError,
    list_project_chunks,
    retrieve_project_chunks,
)
from app.services.qdrant_service import QdrantConfigurationError
from app.services.project_service import (
    build_and_store_project_chunks,
    create_project,
    extract_project_videos,
    get_project_detail,
    get_project_transcript_preview,
    list_projects,
)


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_endpoint(
    payload: ProjectCreateRequest,
) -> ProjectCreateResponse:
    return create_project(payload)


@router.get("", response_model=ProjectListResponse)
def list_projects_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
) -> ProjectListResponse:
    return list_projects(limit=limit)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return get_project_detail(project_id)


@router.get("/{project_id}/transcripts", response_model=TranscriptPreviewResponse)
def get_project_transcript_endpoint(
    project_id: str,
    platform: Platform = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
) -> TranscriptPreviewResponse:
    return get_project_transcript_preview(
        project_id=project_id,
        platform=platform,
        limit=limit,
    )


@router.get("/{project_id}/chunks", response_model=RagChunkListResponse)
def get_project_chunks_endpoint(project_id: str) -> RagChunkListResponse:
    try:
        return list_project_chunks(project_id)
    except RetrievalProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None


@router.post("/{project_id}/chunks/build", response_model=ChunkBuildResponse)
def build_project_chunks_endpoint(project_id: str) -> ChunkBuildResponse:
    return build_and_store_project_chunks(project_id)


@router.post("/{project_id}/index", response_model=IndexProjectResponse)
def index_project_endpoint(project_id: str) -> IndexProjectResponse:
    try:
        return index_project(project_id)
    except ProjectIndexingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None


@router.post("/{project_id}/retrieve", response_model=RetrieveResponse)
def retrieve_project_chunks_endpoint(
    project_id: str,
    payload: RetrieveRequest,
) -> RetrieveResponse:
    try:
        return retrieve_project_chunks(project_id=project_id, request=payload)
    except RetrievalProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except RetrievalValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    except QdrantConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant is not configured.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve chunks from Qdrant.",
        ) from None


@router.post("/{project_id}/extract", response_model=ProjectDetailResponse)
def extract_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return extract_project_videos(project_id)
