from typing import Any

from app.models.rag import (
    RagChunk,
    RagChunkListResponse,
    RetrieveRequest,
    RetrievedChunk,
    RetrieveResponse,
)
from app.services.embedding_service import embed_query
from app.services.qdrant_service import search_project_chunks
from app.services.storage_service import get_project_record, get_rag_chunks


class RetrievalProjectNotFoundError(Exception):
    """Raised when a project cannot be found for retrieval."""


class RetrievalValidationError(Exception):
    """Raised when a retrieval request is invalid."""


def list_project_chunks(project_id: str) -> RagChunkListResponse:
    if get_project_record(project_id) is None:
        raise RetrievalProjectNotFoundError("Project not found.")

    chunks = [RagChunk(**record) for record in get_rag_chunks(project_id)]

    return RagChunkListResponse(
        project_id=project_id,
        total_chunks=len(chunks),
        chunks=chunks,
    )


def retrieve_project_chunks(
    project_id: str,
    request: RetrieveRequest,
) -> RetrieveResponse:
    if get_project_record(project_id) is None:
        raise RetrievalProjectNotFoundError("Project not found.")

    query = request.query.strip()

    if not query:
        raise RetrievalValidationError("Query must not be empty.")

    top_k = max(1, min(request.top_k, 12))
    platform = request.platform
    slot = request.slot
    source_type = request.source_type
    query_vector = embed_query(query)
    search_results = search_project_chunks(
        project_id=project_id,
        query_vector=query_vector,
        top_k=top_k,
        platform=platform,
        slot=slot,
        source_type=source_type,
    )
    retrieved_chunks = [
        chunk
        for result in search_results
        if (chunk := _retrieved_chunk_from_result(result)) is not None
    ]

    return RetrieveResponse(
        project_id=project_id,
        query=query,
        applied_platform=platform,
        applied_slot=slot,
        applied_source_type=source_type,
        total_results=len(retrieved_chunks),
        results=retrieved_chunks,
    )


def retrieve_balanced_evidence(
    project_id: str,
    message: str,
    target_slot: str | None = None,
    reference_slot: str | None = None,
    top_k: int = 12,
) -> RetrieveResponse:
    """Multi-query retrieval that ensures evidence from both content slots for reasoning questions."""
    if get_project_record(project_id) is None:
        raise RetrievalProjectNotFoundError("Project not found.")

    queries = _build_reasoning_queries(message, target_slot, reference_slot)
    per_query_k = min(8, top_k)
    seen_keys: set[str] = set()
    all_chunks: list[RetrievedChunk] = []

    for query in queries:
        query_vector = embed_query(query)
        search_results = search_project_chunks(
            project_id=project_id,
            query_vector=query_vector,
            top_k=per_query_k,
            platform=None,
            slot=None,
            source_type=None,
        )
        for result in search_results:
            chunk = _retrieved_chunk_from_result(result)
            if chunk is None:
                continue
            dedup_key = f"{chunk.citation_label}:{chunk.chunk_index}"
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                all_chunks.append(chunk)

    content_1_chunks = sorted(
        [c for c in all_chunks if c.slot == "content_1"],
        key=lambda c: c.score,
        reverse=True,
    )
    content_2_chunks = sorted(
        [c for c in all_chunks if c.slot == "content_2"],
        key=lambda c: c.score,
        reverse=True,
    )

    # Guarantee at least 3 chunks per slot when available; fill remaining budget from the richer slot.
    half = max(3, top_k // 2)
    c1_take = min(len(content_1_chunks), half)
    c2_take = min(len(content_2_chunks), half)
    remaining = top_k - c1_take - c2_take
    if remaining > 0:
        if len(content_1_chunks) > c1_take:
            c1_take = min(len(content_1_chunks), c1_take + remaining)
        elif len(content_2_chunks) > c2_take:
            c2_take = min(len(content_2_chunks), c2_take + remaining)

    balanced = content_1_chunks[:c1_take] + content_2_chunks[:c2_take]
    balanced.sort(key=lambda c: c.score, reverse=True)

    return RetrieveResponse(
        project_id=project_id,
        query=message,
        applied_platform=None,
        applied_slot=None,
        applied_source_type=None,
        total_results=len(balanced),
        results=balanced,
    )


def _build_reasoning_queries(
    message: str,
    target_slot: str | None,
    reference_slot: str | None,
) -> list[str]:
    if target_slot == "content_2":
        target_label, reference_label = "Content 2", "Content 1"
    else:
        target_label, reference_label = "Content 1", "Content 2"

    return [
        message,
        f"{target_label} hook opening caption description weaknesses areas to improve",
        f"{reference_label} hook opening caption description strengths what works well",
        "compare hook engagement caption CTA improvement recommendations",
    ]


def _retrieved_chunk_from_result(result: dict[str, Any]) -> RetrievedChunk | None:
    payload = result.get("payload")

    if not isinstance(payload, dict):
        return None

    platform = _string_value(payload.get("platform"))
    source_type = _string_value(payload.get("source_type"))
    citation_label = _string_value(payload.get("citation_label"))
    text = _string_value(payload.get("text"))

    if platform is None or source_type is None or citation_label is None or text is None:
        return None

    return RetrievedChunk(
        content_id=_string_value(payload.get("content_id")),
        slot=_string_value(payload.get("slot")),
        platform=platform,
        source_type=source_type,
        score=_float_value(result.get("score")) or 0.0,
        chunk_index=_int_value(payload.get("chunk_index")),
        start_time=_float_value(payload.get("start_time")),
        end_time=_float_value(payload.get("end_time")),
        title=_string_value(payload.get("title")),
        creator=_string_value(payload.get("creator")),
        citation_label=citation_label,
        text=text,
    )


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None
