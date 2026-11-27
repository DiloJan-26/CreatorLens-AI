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


def complete_indexed_job(job_id: str, project_id: str, target: IngestionJobStatus) -> None:
    """Publish indexed readiness and settle its analysis credit in one transaction."""
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.core.access import require_principal, owned_project
    from app.db.models.account import UserEntitlement
    from app.services.account_usage import latest_reservation, complete_owned_analysis

    if target not in {IngestionJobStatus.READY, IngestionJobStatus.PARTIAL_READY}:
        raise ValueError("Only successful indexing can complete an analysis.")
    principal = require_principal()
    with database_session() as session:
        owned_project(session, project_id, principal)
        # Same user lock as API completion; duplicate deliveries cannot consume twice.
        entitlement = session.scalar(select(UserEntitlement).where(
            UserEntitlement.user_id == principal.user_id).with_for_update())
        reservation = latest_reservation(session, project_id)
        job = JobRepository(session).get_for_project(project_id=project_id, job_id=job_id)
        if (not entitlement or not reservation or reservation.user_id != principal.user_id
                or reservation.job_id != job_id or not job):
            raise HTTPException(409, "Indexing does not match the current owned analysis.")
        if reservation.state not in {"reserved", "processing", "completed"}:
            raise HTTPException(409, "Unresolved analysis cannot complete automatically.")
        if job.status != target.value:
            JobRepository(session).transition(job_id, target)
        ProjectRepository(session).update_status(project_id, target.value.lower())
        complete_owned_analysis(session, principal, project_id, False)


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
    from app.services.account_usage import latest_reservation,settle
    with database_session() as session:
        reservation=latest_reservation(session,project_id)
        from app.extraction.policy import ExtractionSafetyError
        from app.db.models.account import ProviderOperation
        from sqlalchemy import select
        uncertain = reservation and session.scalar(select(ProviderOperation.id).where(ProviderOperation.reservation_id==reservation.id,ProviderOperation.state.in_(["admitted","running","needs_reconciliation"])))
        if reservation and isinstance(exc,ExtractionSafetyError) and not uncertain:
            JobRepository(session).fail(job_id,error_code="EXTRACTION_UNAVAILABLE",error_message="Bounded extraction did not provide usable evidence; no provider work remains active.")
            ProjectRepository(session).update_status(project_id,"failed")
            settle(session,reservation.id,"failed",verified_no_active_work=True)
        elif reservation: settle(session,reservation.id,"needs_reconciliation")
        if not reservation or reservation.state!="failed":
            JobRepository(session).fail(job_id,error_code="NEEDS_RECONCILIATION",error_message="Provider/worker outcome requires review; no automatic paid retry.")
    message="Bounded extraction unavailable; analysis credit released." if reservation and reservation.state=="failed" else "Provider/worker outcome requires reconciliation."
    raise WorkerTaskFailedError(message) from None


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
    )
    for secret in secret_values:
        if secret and str(secret) in message:
            message = message.replace(str(secret), "[redacted]")
    message = re.sub(r"https?://\S+", "[external-url]", message)
    message = re.sub(r"rediss?://\S+", "[redis-url]", message)
    return message[:500]

