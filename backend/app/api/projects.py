from fastapi import APIRouter, HTTPException, Query, status

from app.models.project import (
    MetadataAvailabilityResponse,
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
    get_metadata_availability,
    get_project_transcript_preview,
    list_projects,
)


router = APIRouter(prefix="/api/projects")


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["1. Projects"],
    summary="1. Create a two-content comparison",
    description=(
        "Submit two supported public content URLs. Save the returned `project_id`; "
        "the next workflow step is **Extract project content**."
    ),
)
def create_project_endpoint(
    payload: ProjectCreateRequest,
) -> ProjectCreateResponse:
    return create_project(payload)


@router.get(
    "",
    response_model=ProjectListResponse,
    tags=["1. Projects"],
    summary="List recent projects",
    description="Returns persisted comparison projects, newest first.",
)
def list_projects_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
) -> ProjectListResponse:
    return list_projects(limit=limit)


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    tags=["1. Projects"],
    summary="Load a project and its content",
    description="Returns the project plus its latest persisted content metadata.",
)
def get_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return get_project_detail(project_id)


@router.post(
    "/{project_id}/extract",
    response_model=ProjectDetailResponse,
    tags=["2. Content Extraction"],
    summary="1. Extract project content",
    description=(
        "Extracts metadata and transcript evidence for both project URLs and persists "
        "the results. Continue with availability/transcript checks, then build chunks."
    ),
)
def extract_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return extract_project_videos(project_id)


@router.get(
    "/{project_id}/metadata-availability",
    response_model=MetadataAvailabilityResponse,
    tags=["2. Content Extraction"],
    summary="2. Inspect metadata availability",
    description=(
        "Shows which public fields are available or missing after extraction. "
        "Unavailable values are not estimated."
    ),
)
def get_project_metadata_availability_endpoint(
    project_id: str,
) -> MetadataAvailabilityResponse:
    return get_metadata_availability(project_id)


@router.get(
    "/{project_id}/transcripts",
    response_model=TranscriptPreviewResponse,
    tags=["2. Content Extraction"],
    summary="3. Preview extracted transcript evidence",
    description="Inspect transcript segments by content slot or platform after extraction.",
)
def get_project_transcript_endpoint(
    project_id: str,
    platform: Platform | None = Query(default=None),
    slot: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> TranscriptPreviewResponse:
    return get_project_transcript_preview(
        project_id=project_id,
        platform=platform,
        slot=slot,
        limit=limit,
    )


@router.post(
    "/{project_id}/chunks/build",
    response_model=ChunkBuildResponse,
    tags=["3. Evidence Preparation"],
    summary="4. Build evidence chunks",
    description=(
        "Builds and persists metadata, description, hook, and transcript chunks. "
        "Run this after extraction and before indexing."
    ),
)
def build_project_chunks_endpoint(project_id: str) -> ChunkBuildResponse:
    return build_and_store_project_chunks(project_id)


@router.get(
    "/{project_id}/chunks",
    response_model=RagChunkListResponse,
    tags=["3. Evidence Preparation"],
    summary="5. Inspect stored evidence chunks",
    description="Review the chunks produced by the build step before or after indexing.",
)
def get_project_chunks_endpoint(project_id: str) -> RagChunkListResponse:
    try:
        return list_project_chunks(project_id)
    except RetrievalProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None


@router.post(
    "/{project_id}/index",
    response_model=IndexProjectResponse,
    tags=["3. Evidence Preparation"],
    summary="6. Index evidence in Qdrant",
    description="Embeds stored chunks and writes their vectors to Qdrant for retrieval.",
)
def index_project_endpoint(project_id: str) -> IndexProjectResponse:
    try:
        return index_project(project_id)
    except ProjectIndexingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None


@router.post(
    "/{project_id}/retrieve",
    response_model=RetrieveResponse,
    tags=["4. Retrieval & Context"],
    summary="7. Test evidence retrieval",
    description=(
        "Runs semantic retrieval over indexed evidence. Use this to validate results "
        "before testing cited chat."
    ),
)
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
