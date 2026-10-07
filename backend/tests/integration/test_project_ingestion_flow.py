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

    extraction_result = ingestion_tasks.ingest_project_task.run("job-1")

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
    monkeypatch.setattr(
        indexing_tasks,
        "update_project_status",
        lambda _project_id, value: project_statuses.append(value),
    )
    monkeypatch.setattr(
        indexing_tasks,
        "transition_job",
        lambda _job_id, state: transitions.append(state),
    )

    indexing_result = indexing_tasks.index_project_task.run("job-1")

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

    result = ingestion_tasks.ingest_project_task.run("job-1")

    assert result == {
        "job_id": "job-1",
        "status": IngestionJobStatus.EMBEDDING.value,
    }
