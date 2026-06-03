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
