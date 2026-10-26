from app.core.config import Settings
from app.llm.tracing import OptionalTrace, build_trace_metadata


def test_trace_metadata_builder_uses_bounded_operational_fields() -> None:
    metadata = build_trace_metadata(
        project_id="project-1",
        session_id="session-1",
        intent="performance_reasoning",
        retrieval_run_id="retrieval-1",
        prompt_name="comparison_answer",
        prompt_version="1.0.0",
        llm_model="gemini-example",
        retrieved_chunk_count=8,
        source_balance={"content_1": 4, "content_2": 4},
    )

    assert metadata["prompt_version"] == "1.0.0"
    assert metadata["retrieved_chunk_count"] == 8
    assert "api_key" not in metadata
    assert "prompt" not in metadata


def test_disabled_trace_is_a_noop(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    settings = Settings(_env_file=None, LANGSMITH_TRACING=False)

    with OptionalTrace(
        "test",
        run_type="chain",
        inputs={},
        metadata={},
        settings=settings,
    ) as span:
        span.set_outputs({"status": "ok"})

    assert span.trace_id is None
