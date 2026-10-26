from copy import deepcopy
from typing import Any

from app.insights import insight_service
from app.rag import chunk_builder
from app.rag.hybrid_search import build_hybrid_candidates
from app.rag.query_router import classify_question, get_retrieval_plan
from app.rag.reranker import rerank_candidates
from app.schemas.retrieval import RetrievalMode


def test_fixture_flows_through_insights_chunks_routing_and_reranking(
    monkeypatch,
    comparison_project_fixture: dict[str, object],
) -> None:
    project = comparison_project_fixture["project"]
    transcripts = comparison_project_fixture["transcripts"]
    assert isinstance(project, dict)
    assert isinstance(transcripts, dict)

    monkeypatch.setattr(
        chunk_builder,
        "get_project_detail_record",
        lambda _project_id: deepcopy(project),
    )
    monkeypatch.setattr(
        insight_service,
        "get_project_detail_record",
        lambda _project_id: deepcopy(project),
    )

    def _segments(**kwargs: Any) -> list[dict[str, Any]]:
        value = transcripts[kwargs["slot"]]
        assert isinstance(value, list)
        return deepcopy(value)

    monkeypatch.setattr(chunk_builder, "get_transcript_segments", _segments)
    monkeypatch.setattr(insight_service, "get_transcript_segments", _segments)
    monkeypatch.setattr(chunk_builder, "_metric_source_text", lambda *_args: "")

    chunks = chunk_builder.build_project_chunks("fixture-project")
    question = "Why did content 1 perform better than content 2?"
    intent = classify_question(question)
    plan = get_retrieval_plan(intent, question)

    evidence_records = [chunk.model_dump() for chunk in chunks]
    semantic_results = [
        {
            "payload": chunk.model_dump(),
            "score": 0.82 if chunk.slot == "content_1" else 0.74,
        }
        for chunk in chunks
    ]
    candidates = build_hybrid_candidates(
        question,
        evidence_records,
        semantic_results,
    )
    ranked = rerank_candidates(
        candidates,
        mode=plan["mode"],
        top_k=4,
        balance_slots=plan["multi_source"],
    )
    insight = insight_service.get_creator_insight_summary("fixture-project")

    assert plan["mode"] == RetrievalMode.BALANCED_COMPARE
    assert plan["retrieve"] is True
    assert {chunk.slot for chunk in chunks} == {"content_1", "content_2"}
    assert {item.candidate.slot for item in ranked} == {
        "content_1",
        "content_2",
    }
    assert all(item.candidate.citation_label for item in ranked)
    assert len({item.candidate.chunk_id for item in ranked}) == len(ranked)
    assert insight.comparison.confirmed_metric_winner == "Content 1"
    assert insight.comparison.overall_insight_winner == "Content 1"
