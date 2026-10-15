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


def start_project_ingestion(project_id: str) -> IngestionStartResponse:
    settings = get_settings()
    if settings.celery_broker_url is None:
        raise IngestionQueueConfigurationError("Redis is not configured.")

    project_exists = True
    active_job_id: str | None = None
    job_id: str | None = None
    celery_task_id: str | None = None
    try:
        with database_session() as session:
            if ProjectRepository(session).get(project_id) is None:
                project_exists = False
            else:
                repository = JobRepository(session)
                try:
                    job = repository.create(project_id)
                except ActiveIngestionJobError:
                    active = repository.get_active_for_project(project_id)
                    active_job_id = active.id if active is not None else "unknown"
                else:
                    job_id = job.id
                    celery_task_id = str(uuid4())
                    repository.set_task_id(job_id, celery_task_id)
    except IntegrityError:
        active_job_id = _active_job_id(project_id)
        raise ExistingIngestionJobError(job_id=active_job_id or "unknown") from None

    if not project_exists:
        raise IngestionProjectNotFoundError("Project not found.")
    if active_job_id is not None:
        raise ExistingIngestionJobError(job_id=active_job_id)
    if job_id is None or celery_task_id is None:
        raise IngestionQueueUnavailableError(
            "The ingestion job could not be prepared."
        )

    try:
        from app.workers.ingestion_tasks import ingest_project_task

        ingest_project_task.apply_async(
            args=[job_id],
            task_id=celery_task_id,
        )
    except Exception as exc:
        _mark_enqueue_failure(job_id)
        logger.error(
            "Could not enqueue ingestion job job_id=%s project_id=%s "
            "exception_type=%s",
            job_id,
            project_id,
            type(exc).__name__,
        )
        raise IngestionQueueUnavailableError(
            "The ingestion queue is temporarily unavailable."
        ) from None

    logger.info(
        "Ingestion job queued job_id=%s project_id=%s",
        job_id,
        project_id,
    )
    return IngestionStartResponse(
        project_id=project_id,
        job_id=job_id,
        status=IngestionJobStatus.PENDING,
        status_url=f"/api/projects/{project_id}/status?job_id={job_id}",
        message="Ingestion was queued for background processing.",
    )


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

