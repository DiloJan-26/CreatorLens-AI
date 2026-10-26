from typing import Any

from app.models.rag import RetrieveRequest
from app.rag import context_builder, retrieval_service
from app.schemas.retrieval import RetrievalMode


def _evidence_records() -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": "chunk-1",
            "project_id": "project-1",
            "content_id": "item-1",
            "slot": "content_1",
            "platform": "youtube",
            "source_type": "hook",
            "chunk_index": 0,
            "start_time": 0.0,
            "end_time": 4.0,
            "title": "First",
            "creator": "Creator One",
            "text": "A direct opening hook explains the result immediately.",
            "content_hash": "a" * 64,
            "citation_label": "Content 1 hook",
        },
        {
            "chunk_id": "chunk-2",
            "project_id": "project-1",
            "content_id": "item-2",
            "slot": "content_2",
            "platform": "instagram",
            "source_type": "transcript",
            "chunk_index": 0,
            "start_time": 0.0,
            "end_time": 6.0,
            "title": "Second",
            "creator": "Creator Two",
            "text": "This opening builds curiosity before revealing the result.",
            "content_hash": "b" * 64,
            "citation_label": "Content 2 transcript",
        },
    ]


def _configure_retrieval_mocks(monkeypatch) -> list[dict[str, object]]:
    completed_runs: list[dict[str, object]] = []
    monkeypatch.setattr(retrieval_service, "get_project_record", lambda _project_id: {"id": "project-1"})
    monkeypatch.setattr(
        retrieval_service,
        "get_rag_chunks",
        lambda _project_id, _platform=None: _evidence_records(),
    )
    monkeypatch.setattr(retrieval_service, "embed_query", lambda _query: [0.1, 0.2])
    monkeypatch.setattr(retrieval_service, "search_project_chunks", lambda **_kwargs: [])
    monkeypatch.setattr(retrieval_service, "start_retrieval_run", lambda **_kwargs: "run-1")
    monkeypatch.setattr(
        retrieval_service,
        "complete_retrieval_run",
        lambda run_id, **kwargs: completed_runs.append({"run_id": run_id, **kwargs}),
    )
    monkeypatch.setattr(retrieval_service, "fail_retrieval_run", lambda *_args, **_kwargs: None)
    return completed_runs


def test_comparison_retrieval_returns_both_slots_and_citation_fields(monkeypatch) -> None:
    completed_runs = _configure_retrieval_mocks(monkeypatch)
    response = retrieval_service.retrieve_project_chunks(
        "project-1",
        RetrieveRequest(
            query="Why did content 1 perform better than content 2?",
            top_k=2,
        ),
    )

    assert response.retrieval_mode == RetrievalMode.BALANCED_COMPARE
    assert {chunk.slot for chunk in response.results} == {"content_1", "content_2"}

    monkeypatch.setattr(
        context_builder,
        "get_project_detail_record",
        lambda _project_id: {"id": "project-1", "content_items": []},
    )
    monkeypatch.setattr(
        context_builder,
        "build_structured_metadata_context",
        lambda _project_id: "Structured metadata",
    )
    monkeypatch.setattr(context_builder, "retrieve_project_chunks", lambda **_kwargs: response)
    context = context_builder.build_rag_context(
        "project-1",
        "Why did content 1 perform better than content 2?",
    )

    assert {citation.slot for citation in context.citations} == {"content_1", "content_2"}
    assert {citation.source_type for citation in context.citations} == {"hook", "transcript"}
    assert completed_runs[0]["result_chunk_ids"] == [
        chunk.chunk_id for chunk in response.results
    ]


def test_metric_retrieval_does_not_call_embeddings_or_qdrant(monkeypatch) -> None:
    completed_runs = _configure_retrieval_mocks(monkeypatch)
    monkeypatch.setattr(
        retrieval_service,
        "embed_query",
        lambda _query: (_ for _ in ()).throw(AssertionError("embedding called")),
    )
    monkeypatch.setattr(
        retrieval_service,
        "search_project_chunks",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("Qdrant called")),
    )

    response = retrieval_service.retrieve_project_chunks(
        "project-1",
        RetrieveRequest(query="Which content has more confirmed views?"),
    )

    assert response.retrieval_mode == RetrievalMode.METRIC_DIRECT
    assert response.structured_metadata_used is True
    assert response.results == []
    assert completed_runs[0]["candidate_count"] == 0
