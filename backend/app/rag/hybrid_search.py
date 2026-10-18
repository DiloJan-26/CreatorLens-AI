from dataclasses import dataclass
import re
from typing import Any


TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "which",
        "who",
        "why",
        "with",
    }
)


@dataclass(frozen=True)
class HybridCandidate:
    chunk_id: str
    content_id: str | None
    slot: str | None
    platform: str
    source_type: str
    chunk_index: int | None
    start_time: float | None
    end_time: float | None
    title: str | None
    creator: str | None
    citation_label: str
    text: str
    semantic_score: float
    keyword_overlap_score: float


def keyword_overlap_score(query: str, text: str) -> float:
    query_tokens = _meaningful_tokens(query)
    if not query_tokens:
        return 0.0

    text_tokens = _meaningful_tokens(text)
    if not text_tokens:
        return 0.0

    overlap = query_tokens.intersection(text_tokens)
    return len(overlap) / len(query_tokens)


def build_hybrid_candidates(
    query: str,
    evidence_records: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
) -> list[HybridCandidate]:
    semantic_scores: dict[tuple[object, ...], float] = {}
    for result in semantic_results:
        payload = result.get("payload")
        if not isinstance(payload, dict):
            continue
        score = _number(result.get("score"))
        for identity in _identities(payload):
            semantic_scores[identity] = max(semantic_scores.get(identity, 0.0), score)

    candidates: list[HybridCandidate] = []
    for record in evidence_records:
        chunk_id = _text(record.get("chunk_id"))
        platform = _text(record.get("platform"))
        source_type = _text(record.get("source_type"))
        citation_label = _text(record.get("citation_label"))
        text = _text(record.get("text"))
        if not all((chunk_id, platform, source_type, citation_label, text)):
            continue

        semantic_score = max(
            (semantic_scores.get(identity, 0.0) for identity in _identities(record)),
            default=0.0,
        )
        candidates.append(
            HybridCandidate(
                chunk_id=chunk_id,
                content_id=_text(record.get("content_id")),
                slot=_text(record.get("slot")),
                platform=platform,
                source_type=source_type,
                chunk_index=_integer(record.get("chunk_index")),
                start_time=_number_or_none(record.get("start_time")),
                end_time=_number_or_none(record.get("end_time")),
                title=_text(record.get("title")),
                creator=_text(record.get("creator")),
                citation_label=citation_label,
                text=text,
                semantic_score=semantic_score,
                keyword_overlap_score=keyword_overlap_score(query, text),
            )
        )
    return candidates


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if token not in STOP_WORDS and len(token) > 1
    }


def _identities(value: dict[str, Any]) -> list[tuple[object, ...]]:
    identities: list[tuple[object, ...]] = []
    chunk_id = _text(value.get("chunk_id"))
    if chunk_id:
        identities.append(("chunk_id", chunk_id))
    identities.append(
        (
            "location",
            _text(value.get("content_id")),
            _text(value.get("slot")),
            _text(value.get("platform")),
            _text(value.get("source_type")),
            _integer(value.get("chunk_index")),
        )
    )
    return identities


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _number(value: object) -> float:
    number = _number_or_none(value)
    if number is None:
        return 0.0
    return max(0.0, min(number, 1.0))


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None
