import logging
from time import perf_counter
from typing import Any

from app.models.rag import (
    RagChunk,
    RagChunkListResponse,
    RetrieveRequest,
    RetrievedChunk,
    RetrieveResponse,
)
from app.rag.hybrid_search import HybridCandidate, build_hybrid_candidates
from app.rag.query_router import classify_question, get_retrieval_plan
from app.rag.reranker import RankedCandidate, rerank_candidates
from app.schemas.retrieval import (
    RetrievalMode,
    RetrievalRunListResponse,
    RetrievalRunRecord,
)
from app.services.embedding_service import embed_query
from app.services.qdrant_service import search_project_chunks
from app.services.retrieval_run_service import (
    complete_retrieval_run,
    fail_retrieval_run,
    list_project_retrieval_runs,
    start_retrieval_run,
)
from app.services.storage_compat_service import get_project_record, get_rag_chunks


logger = logging.getLogger(__name__)


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


def list_retrieval_runs(
    project_id: str,
    limit: int = 50,
) -> RetrievalRunListResponse:
    if get_project_record(project_id) is None:
        raise RetrievalProjectNotFoundError("Project not found.")
    records = [
        RetrievalRunRecord(**record)
        for record in list_project_retrieval_runs(project_id, limit)
    ]
    return RetrievalRunListResponse(
        project_id=project_id,
        total_runs=len(records),
        runs=records,
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
    mode = request.retrieval_mode or _route_mode(query)
    filters = {
        key: value
        for key, value in {
            "platform": request.platform,
            "slot": request.slot,
            "source_type": request.source_type,
        }.items()
        if value is not None
    }
    started_at = perf_counter()
    run_id = start_retrieval_run(
        project_id=project_id,
        query=query,
        retrieval_mode=mode.value,
        requested_top_k=top_k,
        applied_filters=filters,
    )

    try:
        if mode == RetrievalMode.METRIC_DIRECT:
            response = _metric_direct_response(project_id, query, run_id)
            response.retrieval_latency_ms = _complete_run(
                run_id,
                started_at,
                candidate_count=0,
                results=[],
            )
            return response

        evidence_records = _filtered_evidence_records(
            project_id=project_id,
            platform=request.platform,
            slot=request.slot,
            source_type=request.source_type,
            mode=mode,
        )
        semantic_results = _semantic_results(
            project_id=project_id,
            query=query,
            mode=mode,
            top_k=top_k,
            platform=request.platform,
            slot=request.slot,
            source_type=_semantic_source_filter(request.source_type, mode, evidence_records),
        )
        candidates = build_hybrid_candidates(query, evidence_records, semantic_results)
        ranked = rerank_candidates(
            candidates,
            mode=mode,
            top_k=top_k,
            balance_slots=mode
            in {
                RetrievalMode.BALANCED_COMPARE,
                RetrievalMode.STRATEGY_RECOMMENDATION,
            },
        )
        results = [_retrieved_chunk(item) for item in ranked]
        duration_ms = _complete_run(
            run_id,
            started_at,
            candidate_count=len(candidates),
            results=results,
        )
        logger.info(
            "Retrieval completed project_id=%s run_id=%s mode=%s candidates=%d results=%d",
            project_id,
            run_id,
            mode.value,
            len(candidates),
            len(results),
        )
        return RetrieveResponse(
            project_id=project_id,
            query=query,
            retrieval_mode=mode,
            retrieval_run_id=run_id,
            retrieval_latency_ms=duration_ms,
            structured_metadata_used=False,
            applied_platform=request.platform,
            applied_slot=request.slot,
            applied_source_type=request.source_type,
            total_results=len(results),
            results=results,
        )
    except Exception:
        duration_ms = _duration_ms(started_at)
        fail_retrieval_run(
            run_id,
            error_code="RETRIEVAL_FAILED",
            duration_ms=duration_ms,
        )
        logger.exception(
            "Retrieval failed project_id=%s run_id=%s mode=%s",
            project_id,
            run_id,
            mode.value,
        )
        raise


def retrieve_balanced_evidence(
    project_id: str,
    message: str,
    target_slot: str | None = None,
    reference_slot: str | None = None,
    top_k: int = 12,
) -> RetrieveResponse:
    del target_slot, reference_slot
    return retrieve_project_chunks(
        project_id,
        RetrieveRequest(
            query=message,
            top_k=top_k,
            retrieval_mode=RetrievalMode.BALANCED_COMPARE,
        ),
    )


def _route_mode(query: str) -> RetrievalMode:
    intent = classify_question(query)
    return get_retrieval_plan(intent, query)["mode"]


def _metric_direct_response(
    project_id: str,
    query: str,
    run_id: str | None,
) -> RetrieveResponse:
    logger.info(
        "Structured metadata retrieval selected project_id=%s run_id=%s mode=%s",
        project_id,
        run_id,
        RetrievalMode.METRIC_DIRECT.value,
    )
    return RetrieveResponse(
        project_id=project_id,
        query=query,
        retrieval_mode=RetrievalMode.METRIC_DIRECT,
        retrieval_run_id=run_id,
        structured_metadata_used=True,
        total_results=0,
        results=[],
    )


def _filtered_evidence_records(
    *,
    project_id: str,
    platform: str | None,
    slot: str | None,
    source_type: str | None,
    mode: RetrievalMode,
) -> list[dict[str, Any]]:
    records = get_rag_chunks(project_id, platform)
    if slot is not None:
        records = [record for record in records if record.get("slot") == slot]
    if source_type is not None:
        return [record for record in records if record.get("source_type") == source_type]
    if mode == RetrievalMode.TRANSCRIPT_DEEP:
        transcript_records = [
            record for record in records if record.get("source_type") == "transcript"
        ]
        if transcript_records:
            return transcript_records
    return records


def _semantic_source_filter(
    requested_source_type: str | None,
    mode: RetrievalMode,
    evidence_records: list[dict[str, Any]],
) -> str | None:
    if requested_source_type is not None:
        return requested_source_type
    if mode == RetrievalMode.TRANSCRIPT_DEEP and any(
        record.get("source_type") == "transcript" for record in evidence_records
    ):
        return "transcript"
    return None


def _semantic_results(
    *,
    project_id: str,
    query: str,
    mode: RetrievalMode,
    top_k: int,
    platform: str | None,
    slot: str | None,
    source_type: str | None,
) -> list[dict[str, Any]]:
    candidate_limit = min(max(top_k * 3, 12), 36)
    searches: list[tuple[str, str | None]] = [(query, slot)]

    if slot is None and mode in {
        RetrievalMode.BALANCED_COMPARE,
        RetrievalMode.STRATEGY_RECOMMENDATION,
    }:
        searches = [(query, "content_1"), (query, "content_2")]
    if mode == RetrievalMode.HOOK_FOCUSED:
        searches.append((f"{query} hook opening first seconds", slot))
    elif mode == RetrievalMode.STRATEGY_RECOMMENDATION:
        searches.append((f"{query} strengths weaknesses hook caption CTA", slot))

    results: list[dict[str, Any]] = []
    for search_query, search_slot in searches:
        results.extend(
            search_project_chunks(
                project_id=project_id,
                query_vector=embed_query(search_query),
                top_k=candidate_limit,
                platform=platform,
                slot=search_slot,
                source_type=source_type,
            )
        )
    return results


def _retrieved_chunk(item: RankedCandidate) -> RetrievedChunk:
    candidate: HybridCandidate = item.candidate
    return RetrievedChunk(
        chunk_id=candidate.chunk_id,
        content_id=candidate.content_id,
        slot=candidate.slot,
        platform=candidate.platform,
        source_type=candidate.source_type,
        score=item.final_score,
        chunk_index=candidate.chunk_index,
        start_time=candidate.start_time,
        end_time=candidate.end_time,
        title=candidate.title,
        creator=candidate.creator,
        citation_label=candidate.citation_label,
        text=candidate.text,
    )


def _complete_run(
    run_id: str | None,
    started_at: float,
    *,
    candidate_count: int,
    results: list[RetrievedChunk],
) -> int:
    duration_ms = _duration_ms(started_at)
    complete_retrieval_run(
        run_id,
        candidate_count=candidate_count,
        result_chunk_ids=[chunk.chunk_id for chunk in results if chunk.chunk_id],
        duration_ms=duration_ms,
    )
    return duration_ms


def _duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
