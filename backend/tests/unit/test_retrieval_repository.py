from sqlalchemy.orm import Session

from app.db.repositories.retrieval_repository import RetrievalRepository
from tests.unit.test_content_item_repository import _create_project


def test_retrieval_repository_records_completed_run(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = RetrievalRepository(db_session)
    run = repository.start(
        project_id=project_id,
        query="Which content performed better?",
        retrieval_mode="balanced_compare",
        requested_top_k=8,
        applied_filters={"slots": ["content_1", "content_2"]},
    )

    assert repository.complete(
        run.id,
        candidate_count=14,
        result_chunk_ids=["chunk-1", "chunk-2"],
        duration_ms=42,
    )

    record = repository.get(run.id)
    assert record is not None
    assert record["status"] == "COMPLETED"
    assert record["candidate_count"] == 14
    assert record["result_count"] == 2
    assert record["result_chunk_ids"] == ["chunk-1", "chunk-2"]
    assert record["duration_ms"] == 42
    assert repository.list_for_project(project_id)[0]["id"] == run.id


def test_retrieval_repository_records_safe_failure(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = RetrievalRepository(db_session)
    run = repository.start(
        project_id=project_id,
        query="Explain the opening hook.",
        retrieval_mode="hook_focused",
        requested_top_k=6,
    )

    assert repository.fail(
        run.id,
        error_code="VECTOR_STORE_UNAVAILABLE",
        duration_ms=17,
    )

    record = repository.get(run.id)
    assert record is not None
    assert record["status"] == "FAILED"
    assert record["error_code"] == "VECTOR_STORE_UNAVAILABLE"
    assert record["duration_ms"] == 17
    assert record["completed_at"] is not None
