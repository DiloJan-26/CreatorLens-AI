from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.ingestion_job import IngestionJob
from app.db.repositories._utils import utc_now
from app.schemas.ingestion import (
    IngestionJobStatus,
    TERMINAL_JOB_STATUSES,
    can_transition_job,
)


class IngestionJobNotFoundError(LookupError):
    """Raised when an ingestion job cannot be found."""


class InvalidIngestionJobTransitionError(ValueError):
    """Raised when a job attempts an illegal state transition."""


class ActiveIngestionJobError(RuntimeError):
    """Raised when a project already has a non-terminal ingestion job."""


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, project_id: str) -> IngestionJob:
        if self.get_active_for_project(project_id) is not None:
            raise ActiveIngestionJobError(
                "An ingestion job is already active for this project."
            )

        timestamp = utc_now()
        job = IngestionJob(
            id=str(uuid4()),
            project_id=project_id,
            status=IngestionJobStatus.PENDING.value,
            retry_count=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: str) -> IngestionJob | None:
        return self.session.get(IngestionJob, job_id)

    def get_for_project(
        self,
        *,
        project_id: str,
        job_id: str,
    ) -> IngestionJob | None:
        return self.session.scalar(
            select(IngestionJob).where(
                IngestionJob.id == job_id,
                IngestionJob.project_id == project_id,
            )
        )

    def get_latest_for_project(self, project_id: str) -> IngestionJob | None:
        return self.session.scalar(
            select(IngestionJob)
            .where(IngestionJob.project_id == project_id)
            .order_by(desc(IngestionJob.created_at))
            .limit(1)
        )

    def get_active_for_project(self, project_id: str) -> IngestionJob | None:
        terminal_values = [status.value for status in TERMINAL_JOB_STATUSES]
        return self.session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.project_id == project_id,
                IngestionJob.status.not_in(terminal_values),
            )
            .order_by(desc(IngestionJob.created_at))
            .limit(1)
        )

    def set_task_id(self, job_id: str, celery_task_id: str) -> IngestionJob:
        job = self._require(job_id)
        job.celery_task_id = celery_task_id
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def transition(
        self,
        job_id: str,
        target: IngestionJobStatus,
    ) -> IngestionJob:
        job = self._require(job_id)
        current = IngestionJobStatus(job.status)
        if not can_transition_job(current, target):
            raise InvalidIngestionJobTransitionError(
                f"Cannot transition ingestion job from {current.value} "
                f"to {target.value}."
            )

        timestamp = utc_now()
        job.status = target.value
        job.updated_at = timestamp
        if job.started_at is None and target != IngestionJobStatus.PENDING:
            job.started_at = timestamp
        if target in TERMINAL_JOB_STATUSES:
            job.completed_at = timestamp
        if target != IngestionJobStatus.FAILED:
            job.error_code = None
            job.error_message = None
        self.session.flush()
        return job

    def restart_for_retry(
        self,
        job_id: str,
        target: IngestionJobStatus,
    ) -> IngestionJob:
        job = self._require(job_id)
        if IngestionJobStatus(job.status) in TERMINAL_JOB_STATUSES:
            raise InvalidIngestionJobTransitionError(
                "A terminal ingestion job cannot be restarted."
            )
        job.status = target.value
        job.updated_at = utc_now()
        job.error_code = None
        job.error_message = None
        self.session.flush()
        return job

    def record_retry(
        self,
        job_id: str,
        *,
        retry_count: int,
        error_code: str,
        error_message: str,
    ) -> IngestionJob:
        job = self._require(job_id)
        job.retry_count = max(job.retry_count, retry_count)
        job.error_code = error_code[:64]
        job.error_message = error_message[:500]
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def fail(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> IngestionJob:
        job = self._require(job_id)
        timestamp = utc_now()
        job.status = IngestionJobStatus.FAILED.value
        job.error_code = error_code[:64]
        job.error_message = error_message[:500]
        job.updated_at = timestamp
        job.completed_at = timestamp
        if job.started_at is None:
            job.started_at = timestamp
        self.session.flush()
        return job

    @staticmethod
    def to_record(job: IngestionJob) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "project_id": job.project_id,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "retry_count": job.retry_count,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": _aware(job.created_at),
            "updated_at": _aware(job.updated_at),
            "started_at": _aware(job.started_at),
            "completed_at": _aware(job.completed_at),
        }

    def _require(self, job_id: str) -> IngestionJob:
        job = self.get(job_id)
        if job is None:
            raise IngestionJobNotFoundError("Ingestion job not found.")
        return job


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)

