import logging
import re
from typing import Any

from celery import Task

from app.core.config import get_settings
from app.db.repositories.job_repository import JobRepository
from app.db.repositories.project_repository import ProjectRepository
from app.db.session import database_session
from app.schemas.ingestion import (
    IngestionJobStatus,
    TERMINAL_JOB_STATUSES,
)


logger = logging.getLogger(__name__)


class WorkerTaskFailedError(RuntimeError):
    """Safe exception surfaced to Celery after job failure is persisted."""


def job_context(job_id: str) -> tuple[str, IngestionJobStatus]:
    with database_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise WorkerTaskFailedError("Persisted ingestion job was not found.")
        return job.project_id, IngestionJobStatus(job.status)


def transition_job(job_id: str, target: IngestionJobStatus) -> None:
    with database_session() as session:
        JobRepository(session).transition(job_id, target)


def start_or_restart_job(job_id: str, target: IngestionJobStatus) -> bool:
    with database_session() as session:
        repository = JobRepository(session)
        job = repository.get(job_id)
        if job is None:
            raise WorkerTaskFailedError("Persisted ingestion job was not found.")
        current = IngestionJobStatus(job.status)
        if current in TERMINAL_JOB_STATUSES:
            return False
        if current == IngestionJobStatus.PENDING or (
            current == IngestionJobStatus.CHUNKING
            and target == IngestionJobStatus.EMBEDDING
        ):
            repository.transition(job_id, target)
        else:
            repository.restart_for_retry(job_id, target)
        return True


def set_job_task_id(job_id: str, task_id: str) -> None:
    with database_session() as session:
        JobRepository(session).set_task_id(job_id, task_id)


def retry_or_fail_job(
    task: Task,
    *,
    job_id: str,
    project_id: str,
    exc: Exception,
    error_code: str,
    fallback_message: str,
) -> None:
    settings = get_settings()
    safe_message = safe_worker_error(exc, fallback=fallback_message)
    next_retry = int(task.request.retries) + 1

    if int(task.request.retries) < settings.celery_max_retries:
        with database_session() as session:
            JobRepository(session).record_retry(
                job_id,
                retry_count=next_retry,
                error_code=f"{error_code}_RETRY",
                error_message=safe_message,
            )
        countdown = settings.celery_retry_backoff_seconds * (
            2 ** int(task.request.retries)
        )
        logger.warning(
            "Worker job scheduled for retry job_id=%s project_id=%s "
            "error_code=%s retry_count=%s exception_type=%s",
            job_id,
            project_id,
            error_code,
            next_retry,
            type(exc).__name__,
        )
        raise task.retry(
            exc=WorkerTaskFailedError(safe_message),
            countdown=countdown,
            max_retries=settings.celery_max_retries,
        )

    with database_session() as session:
        JobRepository(session).fail(
            job_id,
            error_code=error_code,
            error_message=safe_message,
        )
        ProjectRepository(session).update_status(project_id, "failed")

    logger.error(
        "Worker job failed job_id=%s project_id=%s error_code=%s "
        "retry_count=%s exception_type=%s",
        job_id,
        project_id,
        error_code,
        task.request.retries,
        type(exc).__name__,
    )
    raise WorkerTaskFailedError(safe_message) from None


def safe_worker_error(exc: Exception, *, fallback: str) -> str:
    settings = get_settings()
    raw_message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    message = raw_message or fallback
    secret_values: tuple[Any, ...] = (
        settings.redis_url,
        settings.celery_broker_url_override,
        settings.celery_result_backend_override,
        settings.database_url,
        settings.gemini_api_key,
        settings.qdrant_api_key,
        settings.qdrant_url,
        settings.youtube_api_key,
        settings.apify_api_token,
        settings.deepgram_api_key,
        settings.assemblyai_api_key,
    )
    for secret in secret_values:
        if secret and str(secret) in message:
            message = message.replace(str(secret), "[redacted]")
    message = re.sub(r"https?://\S+", "[external-url]", message)
    message = re.sub(r"rediss?://\S+", "[redis-url]", message)
    return message[:500]

