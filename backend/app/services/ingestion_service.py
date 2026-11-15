import logging
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.repositories.job_repository import (
    ActiveIngestionJobError,
    JobRepository,
)
from app.db.repositories.project_repository import ProjectRepository
from app.db.session import database_session
from app.schemas.ingestion import (
    JOB_PROGRESS_PERCENT,
    IngestionJobStatus,
    IngestionStartResponse,
    IngestionStatusResponse,
)


logger = logging.getLogger(__name__)


class IngestionProjectNotFoundError(LookupError):
    """Raised when ingestion is requested for an unknown project."""


class IngestionJobNotFoundError(LookupError):
    """Raised when no matching persisted ingestion job exists."""


class IngestionQueueConfigurationError(RuntimeError):
    """Raised when Redis is not configured for the API process."""


class IngestionQueueUnavailableError(RuntimeError):
    """Raised when the API cannot publish a job to Celery."""


class ExistingIngestionJobError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"An ingestion job is already active: {job_id}.")
        self.job_id = job_id


def start_project_ingestion(project_id: str, idempotency_key: str | None = None) -> IngestionStartResponse:
    settings = get_settings()
    from app.services.admitted_ingestion import start
    return start(project_id,idempotency_key)


def get_project_ingestion_status(
    project_id: str,
    *,
    job_id: str | None = None,
) -> IngestionStatusResponse:
    project_exists = True
    record = None
    with database_session() as session:
        if ProjectRepository(session).get(project_id) is None:
            project_exists = False
        else:
            repository = JobRepository(session)
            job = (
                repository.get_for_project(project_id=project_id, job_id=job_id)
                if job_id is not None
                else repository.get_latest_for_project(project_id)
            )
            if job is not None:
                record = repository.to_record(job)

    if not project_exists:
        raise IngestionProjectNotFoundError("Project not found.")
    if record is None:
        raise IngestionJobNotFoundError("Ingestion job not found.")

    status = IngestionJobStatus(record["status"])
    return IngestionStatusResponse(
        project_id=project_id,
        job_id=str(record["job_id"]),
        status=status,
        progress_percent=JOB_PROGRESS_PERCENT[status],
        retry_count=int(record["retry_count"]),
        error_code=record["error_code"],
        error_message=record["error_message"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        started_at=record["started_at"],
        completed_at=record["completed_at"],
    )


def _active_job_id(project_id: str) -> str | None:
    with database_session() as session:
        job = JobRepository(session).get_active_for_project(project_id)
        return job.id if job is not None else None


def _mark_enqueue_failure(job_id: str) -> None:
    with database_session() as session:
        JobRepository(session).fail(
            job_id,
            error_code="QUEUE_UNAVAILABLE",
            error_message="The ingestion queue could not accept this job.",
        )

