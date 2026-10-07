from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.repositories.job_repository import (
    ActiveIngestionJobError,
    InvalidIngestionJobTransitionError,
    JobRepository,
)
from app.db.repositories.project_repository import ProjectRepository
from app.schemas.ingestion import IngestionJobStatus


def _create_project(session: Session) -> str:
    project_id = str(uuid4())
    ProjectRepository(session).create(
        project_id=project_id,
        content_1_url="https://youtube.com/shorts/one",
        content_2_url="https://instagram.com/reel/two",
        content_1_platform="youtube",
        content_2_platform="instagram",
        status="created",
    )
    return project_id


def test_job_repository_persists_transitions_and_completion(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    repository = JobRepository(db_session)
    job = repository.create(project_id)

    assert job.status == IngestionJobStatus.PENDING.value
    repository.transition(job.id, IngestionJobStatus.EXTRACTING_METADATA)
    repository.transition(job.id, IngestionJobStatus.EXTRACTING_TRANSCRIPT)
    repository.transition(job.id, IngestionJobStatus.CHUNKING)
    repository.transition(job.id, IngestionJobStatus.EMBEDDING)
    repository.transition(job.id, IngestionJobStatus.INDEXING)
    completed = repository.transition(job.id, IngestionJobStatus.READY)

    assert completed.started_at is not None
    assert completed.completed_at is not None
    assert repository.get_active_for_project(project_id) is None
    assert repository.get_latest_for_project(project_id) is completed


def test_repository_rejects_second_active_job(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = JobRepository(db_session)
    repository.create(project_id)

    with pytest.raises(ActiveIngestionJobError):
        repository.create(project_id)


def test_repository_rejects_invalid_transition(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = JobRepository(db_session)
    job = repository.create(project_id)

    with pytest.raises(InvalidIngestionJobTransitionError):
        repository.transition(job.id, IngestionJobStatus.INDEXING)


def test_repository_saves_retry_and_failure_context(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = JobRepository(db_session)
    job = repository.create(project_id)
    repository.transition(job.id, IngestionJobStatus.EXTRACTING_METADATA)
    repository.record_retry(
        job.id,
        retry_count=1,
        error_code="INGESTION_FAILED_RETRY",
        error_message="Temporary provider failure.",
    )
    failed = repository.fail(
        job.id,
        error_code="INGESTION_FAILED",
        error_message="Provider remained unavailable.",
    )

    assert failed.status == IngestionJobStatus.FAILED.value
    assert failed.retry_count == 1
    assert failed.error_code == "INGESTION_FAILED"
    assert failed.error_message == "Provider remained unavailable."
    assert failed.completed_at is not None

