from sqlalchemy.orm import Session

from app.db.repositories.llm_run_repository import LlmRunRepository
from app.llm.token_usage import TokenUsage
from tests.unit.test_content_item_repository import _create_project


def test_llm_run_repository_records_completed_run(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = LlmRunRepository(db_session)
    run = repository.start(
        project_id=project_id,
        session_id="session-1",
        llm_provider="gemini",
        llm_model="gemini-example",
        prompt_name="comparison_answer",
        prompt_version="1.0.0",
        retrieved_chunk_count=8,
        source_balance={"content_1": 4, "content_2": 4},
    )

    assert repository.complete(
        run.id,
        usage=TokenUsage(120, 30, 150),
        retrieval_latency_ms=42,
        llm_latency_ms=310,
        cache_hit=True,
        cache_miss=False,
        transcript_provider="supadata_platform_captions",
        transcript_fallback_used=False,
        embedding_reused=True,
        langsmith_trace_id="trace-1",
    )

    record = repository.get(run.id)
    assert record is not None
    assert record["status"] == "COMPLETED"
    assert record["prompt_version"] == "1.0.0"
    assert record["total_tokens"] == 150
    assert record["retrieval_latency_ms"] == 42
    assert record["llm_latency_ms"] == 310
    assert record["source_balance"] == {"content_1": 4, "content_2": 4}
    assert record["langsmith_trace_id"] == "trace-1"


def test_llm_run_repository_preserves_unavailable_usage(db_session: Session) -> None:
    project_id = _create_project(db_session)
    repository = LlmRunRepository(db_session)
    run = repository.start(
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        prompt_name="metric_answer",
        prompt_version="1.0.0",
    )

    assert repository.fail(
        run.id,
        error_code="MODEL_UNAVAILABLE",
        usage=TokenUsage(),
        llm_latency_ms=20,
    )

    record = repository.get(run.id)
    assert record is not None
    assert record["status"] == "FAILED"
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["total_tokens"] is None
    assert record["error_code"] == "MODEL_UNAVAILABLE"
