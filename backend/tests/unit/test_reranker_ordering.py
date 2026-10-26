from app.rag.hybrid_search import HybridCandidate
from app.rag.reranker import rerank_candidates
from app.schemas.retrieval import RetrievalMode


def _candidate(
    chunk_id: str,
    *,
    slot: str,
    source_type: str,
    semantic_score: float,
    keyword_score: float,
) -> HybridCandidate:
    return HybridCandidate(
        chunk_id=chunk_id,
        content_id=f"content-{slot}",
        slot=slot,
        platform="youtube",
        source_type=source_type,
        chunk_index=0,
        start_time=None,
        end_time=None,
        title=None,
        creator=None,
        citation_label=chunk_id,
        text="evidence",
        semantic_score=semantic_score,
        keyword_overlap_score=keyword_score,
    )


def test_hook_mode_prioritizes_hook_when_relevance_is_equal() -> None:
    ranked = rerank_candidates(
        [
            _candidate(
                "metadata",
                slot="content_1",
                source_type="metadata",
                semantic_score=0.8,
                keyword_score=0.5,
            ),
            _candidate(
                "hook",
                slot="content_1",
                source_type="hook",
                semantic_score=0.8,
                keyword_score=0.5,
            ),
        ],
        mode=RetrievalMode.HOOK_FOCUSED,
        top_k=2,
    )

    assert ranked[0].candidate.chunk_id == "hook"


def test_balanced_compare_selects_both_slots() -> None:
    ranked = rerank_candidates(
        [
            _candidate(
                "one-a",
                slot="content_1",
                source_type="transcript",
                semantic_score=0.9,
                keyword_score=0.8,
            ),
            _candidate(
                "one-b",
                slot="content_1",
                source_type="hook",
                semantic_score=0.85,
                keyword_score=0.8,
            ),
            _candidate(
                "two-a",
                slot="content_2",
                source_type="transcript",
                semantic_score=0.4,
                keyword_score=0.3,
            ),
        ],
        mode=RetrievalMode.BALANCED_COMPARE,
        top_k=2,
        balance_slots=True,
    )

    assert {item.candidate.slot for item in ranked} == {"content_1", "content_2"}
