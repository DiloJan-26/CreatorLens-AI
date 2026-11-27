"""Pipeline-stage tests; signed route-to-owned-worker acceptance is tested separately."""
import pytest
from contextlib import contextmanager
from types import SimpleNamespace

from app.schemas.ingestion import IngestionJobStatus
from app.workers import indexing_tasks, ingestion_tasks


def test_worker_pipeline_reaches_ready_without_runtime_services(monkeypatch) -> None:
    transitions: list[IngestionJobStatus] = []
    project_statuses: list[str] = []

    monkeypatch.setattr(
        ingestion_tasks,
        "job_context",
        lambda _job_id: ("project-1", IngestionJobStatus.PENDING),
    )
    monkeypatch.setattr(ingestion_tasks, "start_or_restart_job", lambda *_: True)
    monkeypatch.setattr(ingestion_tasks, "extract_project_videos", lambda *_: None)
    monkeypatch.setattr(
        ingestion_tasks,
        "transition_job",
        lambda _job_id, state: transitions.append(state),
    )
    monkeypatch.setattr(
        ingestion_tasks,
        "build_and_store_project_chunks",
        lambda *_: SimpleNamespace(total_chunks=4),
    )
    monkeypatch.setattr(
        indexing_tasks.index_project_task,
        "apply_async",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(ingestion_tasks, "set_job_task_id", lambda *_: None)

    extraction_result = ingestion_tasks.ingest_project_task.run.__wrapped__(ingestion_tasks.ingest_project_task,"job-1")

    assert extraction_result["status"] == IngestionJobStatus.CHUNKING.value
    assert transitions == [
        IngestionJobStatus.EXTRACTING_TRANSCRIPT,
        IngestionJobStatus.CHUNKING,
    ]

    transitions.clear()
    monkeypatch.setattr(
        indexing_tasks,
        "job_context",
        lambda _job_id: ("project-1", IngestionJobStatus.CHUNKING),
    )
    monkeypatch.setattr(indexing_tasks, "start_or_restart_job", lambda *_: True)
    monkeypatch.setattr(
        indexing_tasks,
        "index_project",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="indexed",
            message=None,
            total_chunks=4,
        ),
    )
    monkeypatch.setattr(
        indexing_tasks,
        "list_video_records",
        lambda *_: [
            {"extraction_status": "ready", "transcript_available": True},
            {"extraction_status": "ready", "transcript_available": True},
        ],
    )
    def complete_indexed(job_id, project_id, target):
        assert job_id == "job-1" and project_id == "project-1"
        project_statuses.append(target.value.lower())
        transitions.append(target)
    monkeypatch.setattr(indexing_tasks, "complete_indexed_job", complete_indexed)
    monkeypatch.setattr(
        indexing_tasks,
        "transition_job",
        lambda _job_id, state: transitions.append(state),
    )

    indexing_result = indexing_tasks.index_project_task.run.__wrapped__(indexing_tasks.index_project_task,"job-1")

    assert indexing_result["status"] == IngestionJobStatus.READY.value
    assert transitions == [
        IngestionJobStatus.INDEXING,
        IngestionJobStatus.READY,
    ]
    assert project_statuses == ["ready"]


def test_duplicate_ingestion_delivery_does_not_restart_indexing(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestion_tasks,
        "job_context",
        lambda _job_id: ("project-1", IngestionJobStatus.EMBEDDING),
    )

    result = ingestion_tasks.ingest_project_task.run.__wrapped__(ingestion_tasks.ingest_project_task,"job-1")

    assert result == {
        "job_id": "job-1",
        "status": IngestionJobStatus.EMBEDDING.value,
    }


@pytest.fixture(autouse=True)
def authorized_pipeline_stage_fixture(monkeypatch):
    from app.core.access import current_principal
    from app.core.identity import Principal
    principal=current_principal.set(Principal("offline-pipeline-user","offline-session",1))
    @contextmanager
    def database():yield SimpleNamespace()
    monkeypatch.setattr("app.db.session.database_session",database)
    monkeypatch.setattr("app.services.account_usage.latest_reservation",lambda *args:SimpleNamespace(id="offline-reservation"))
    monkeypatch.setattr("app.workers.owned_execution.queue_index",lambda *args:None)
    try:yield
    finally:current_principal.reset(principal)
