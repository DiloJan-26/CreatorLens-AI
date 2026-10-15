from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.ingestion import IngestionStartResponse, IngestionStatusResponse
from app.services.ingestion_service import (
    ExistingIngestionJobError,
    IngestionJobNotFoundError,
    IngestionProjectNotFoundError,
    IngestionQueueConfigurationError,
    IngestionQueueUnavailableError,
    get_project_ingestion_status,
    start_project_ingestion,
)


router = APIRouter(prefix="/api/projects", tags=["2. Async Ingestion"])


@router.post(
    "/{project_id}/ingest",
    response_model=IngestionStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start background project ingestion",
    description=(
        "Queues metadata extraction, transcript processing, evidence chunking, "
        "embedding, and Qdrant indexing. Poll the returned `status_url`."
    ),
)
def start_ingestion_endpoint(project_id: str) -> IngestionStartResponse:
    try:
        return start_project_ingestion(project_id)
    except IngestionProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except ExistingIngestionJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An ingestion job is already active for this project: "
                f"{exc.job_id}."
            ),
        ) from None
    except IngestionQueueConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background ingestion is not configured.",
        ) from None
    except IngestionQueueUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The ingestion queue is temporarily unavailable.",
        ) from None


@router.get(
    "/{project_id}/status",
    response_model=IngestionStatusResponse,
    summary="Get background ingestion status",
    description=(
        "Returns the latest persisted ingestion job for the project, or the "
        "specific job selected with `job_id`."
    ),
)
def get_ingestion_status_endpoint(
    project_id: str,
    job_id: str | None = Query(default=None),
) -> IngestionStatusResponse:
    try:
        return get_project_ingestion_status(project_id, job_id=job_id)
    except IngestionProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except IngestionJobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found.",
        ) from None
