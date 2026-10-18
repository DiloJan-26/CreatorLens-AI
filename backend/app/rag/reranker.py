from dataclasses import dataclass

from app.rag.hybrid_search import HybridCandidate
from app.schemas.retrieval import RetrievalMode


SEMANTIC_WEIGHT = 0.55
KEYWORD_WEIGHT = 0.25
SOURCE_TYPE_WEIGHT = 0.10
SLOT_BALANCE_WEIGHT = 0.10


@dataclass(frozen=True)
class RankedCandidate:
    candidate: HybridCandidate
    final_score: float
    source_type_boost: float
    slot_balance_bonus: float


SOURCE_TYPE_BOOSTS: dict[RetrievalMode, dict[str, float]] = {
    RetrievalMode.METRIC_DIRECT: {
        "metadata": 1.0,
        "description": 0.3,
        "hook": 0.2,
        "transcript": 0.2,
    },
    RetrievalMode.HOOK_FOCUSED: {
        "hook": 1.0,
        "transcript": 0.85,
        "description": 0.5,
        "metadata": 0.25,
    },
    RetrievalMode.BALANCED_COMPARE: {
        "hook": 1.0,
        "transcript": 0.9,
        "description": 0.8,
        "metadata": 0.7,
    },
    RetrievalMode.TRANSCRIPT_DEEP: {
        "transcript": 1.0,
        "hook": 0.7,
        "description": 0.4,
        "metadata": 0.25,
    },
    RetrievalMode.STRATEGY_RECOMMENDATION: {
        "hook": 1.0,
        "transcript": 1.0,
        "description": 0.9,
        "metadata": 0.8,
    },
}


def source_type_boost(mode: RetrievalMode, source_type: str) -> float:
    return SOURCE_TYPE_BOOSTS[mode].get(source_type, 0.0)


def slot_balance_bonus(
    slot: str | None,
    selected_slots: set[str],
    desired_slots: set[str],
) -> float:
    if slot is None or slot not in desired_slots:
        return 0.0
    return 1.0 if slot not in selected_slots else 0.0


def rerank_candidates(
    candidates: list[HybridCandidate],
    *,
    mode: RetrievalMode,
    top_k: int,
    balance_slots: bool = False,
) -> list[RankedCandidate]:
    safe_top_k = max(1, min(top_k, 12))
    desired_slots = (
        {candidate.slot for candidate in candidates if candidate.slot in {"content_1", "content_2"}}
        if balance_slots
        else set()
    )
    selected: list[RankedCandidate] = []
    selected_ids: set[str] = set()
    selected_slots: set[str] = set()

    while len(selected) < safe_top_k:
        remaining = [candidate for candidate in candidates if candidate.chunk_id not in selected_ids]
        if not remaining:
            break

        missing_slots = desired_slots - selected_slots
        eligible = (
            [candidate for candidate in remaining if candidate.slot in missing_slots]
            if missing_slots and selected
            else remaining
        )
        ranked = [
            _score_candidate(candidate, mode, selected_slots, desired_slots)
            for candidate in eligible
        ]
        best = max(
            ranked,
            key=lambda item: (
                item.final_score,
                item.candidate.semantic_score,
                item.candidate.keyword_overlap_score,
                item.candidate.chunk_id,
            ),
        )
        selected.append(best)
        selected_ids.add(best.candidate.chunk_id)
        if best.candidate.slot:
            selected_slots.add(best.candidate.slot)

    return selected


def _score_candidate(
    candidate: HybridCandidate,
    mode: RetrievalMode,
    selected_slots: set[str],
    desired_slots: set[str],
) -> RankedCandidate:
    source_boost = source_type_boost(mode, candidate.source_type)
    balance_bonus = slot_balance_bonus(candidate.slot, selected_slots, desired_slots)
    final_score = (
        SEMANTIC_WEIGHT * candidate.semantic_score
        + KEYWORD_WEIGHT * candidate.keyword_overlap_score
        + SOURCE_TYPE_WEIGHT * source_boost
        + SLOT_BALANCE_WEIGHT * balance_bonus
    )
    return RankedCandidate(
        candidate=candidate,
        final_score=round(final_score, 6),
        source_type_boost=source_boost,
        slot_balance_bonus=balance_bonus,
    )
