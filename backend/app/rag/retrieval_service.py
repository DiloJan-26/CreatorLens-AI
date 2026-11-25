import logging
import math
import re
from time import perf_counter
from typing import Any

from app.models.rag import (
    RagChunk,
    RagChunkListResponse,
    RetrieveRequest,
    RetrievedChunk,
    RetrievalDiagnostics,
    RetrievalMatchDetails,
    RetrieveResponse,
)
from app.rag.hybrid_search import HybridCandidate, build_hybrid_candidates, matching_query_terms
from app.rag.query_router import classify_question, get_retrieval_plan
from app.rag.reranker import (RankedCandidate, rerank_candidates, SEMANTIC_WEIGHT, KEYWORD_WEIGHT, SOURCE_TYPE_WEIGHT, SLOT_BALANCE_WEIGHT)
from app.core.config import get_settings
from app.services.hash_service import hash_payload
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
    evidence_search = request.purpose == "evidence_search"
    if evidence_search and len(query) > 1000:
        raise RetrievalValidationError("Evidence queries must be at most 1,000 characters.")
    filters = {
        key: value
        for key, value in {
            "platform": request.platform,
            "slot": request.slot,
            "source_type": request.source_type,
        }.items()
        if value is not None
    }
    if evidence_search:
        filters["purpose"] = request.purpose
    started_at = perf_counter()
    run_id = start_retrieval_run(
        project_id=project_id,
        query=query,
        retrieval_mode=mode.value,
        requested_top_k=top_k,
        applied_filters=filters,
    )

    try:
        if mode == RetrievalMode.METRIC_DIRECT and not evidence_search:
            response = _metric_direct_response(project_id, query, run_id)
            response.retrieval_latency_ms = _complete_run(
                run_id,
                started_at,
                candidate_count=0,
                results=[],
            )
            return response

        # Reuse query routing and ranking; Evidence must retrieve passages even for metrics.
        # Only this explicit purpose requires vector-backed candidate membership.
        settings = get_settings() if evidence_search else None
        from app.services.evidence_window import requested_verbal_window
        window_seconds = requested_verbal_window(query)
        evidence_records = _filtered_evidence_records(
            project_id=project_id,
            platform=request.platform,
            slot=request.slot,
            source_type=request.source_type,
            mode=mode,
        )
        initial_snapshot = _evidence_snapshot(evidence_records) if evidence_search else None
        if evidence_search:
            evidence_records = [r for r in evidence_records if r.get("project_id") == project_id]
        if window_seconds is not None:
            evidence_records = [r for r in evidence_records if r.get("source_type") not in {"hook", "transcript"}
                or (isinstance(r.get("start_time"), (int, float)) and isinstance(r.get("end_time"), (int, float))
                    and 0 <= r["start_time"] < r["end_time"] <= window_seconds)]
        semantic_results = _semantic_results(
            project_id=project_id,
            query=query,
            mode=mode,
            top_k=top_k,
            platform=request.platform,
            slot=request.slot,
            source_type=_semantic_source_filter(request.source_type, mode, evidence_records),
        )
        raw_match_count = len(semantic_results)
        rejected_matches = False
        if evidence_search:
            semantic_results = _validated_vector_matches(project_id, evidence_records, semantic_results, settings)
            rejected_matches = len(semantic_results) < raw_match_count
        candidates = build_hybrid_candidates(query, evidence_records, semantic_results)
        if evidence_search:
            vector_ids = {r["payload"]["chunk_id"] for r in semantic_results}
            candidates = [c for c in candidates if c.chunk_id in vector_ids and c.semantic_score > 0]

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
        if evidence_search:
            current_records = _filtered_evidence_records(project_id=project_id, platform=request.platform,
                slot=request.slot, source_type=request.source_type, mode=mode)
            if _evidence_snapshot(current_records) != initial_snapshot:
                raise RetrievalValidationError("Source evidence changed during search. Please retry.")
            for rank, (result, item) in enumerate(zip(results, ranked, strict=True), 1):
                result.match_details = RetrievalMatchDetails(rank=rank, vector_match=True,
                    semantic_similarity=item.candidate.semantic_score,
                    keyword_overlap=item.candidate.keyword_overlap_score,
                    matching_terms=matching_query_terms(query, item.candidate.text),
                    contributions={"semantic": SEMANTIC_WEIGHT * item.candidate.semantic_score,
                        "keyword": KEYWORD_WEIGHT * item.candidate.keyword_overlap_score,
                        "source": SOURCE_TYPE_WEIGHT * item.source_type_boost,
                        "balance": SLOT_BALANCE_WEIGHT * item.slot_balance_bonus})

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
            purpose=request.purpose,
            diagnostics=RetrievalDiagnostics(embedding_model=settings.embedding_model_name,
                embedding_version=settings.embedding_model_version,
                vector_matches=len({r["payload"]["chunk_id"] for r in semantic_results}),
                eligible_candidates=len(candidates),
                returned_by_slot={slot: sum(c.slot == slot for c in results) for slot in ("content_1", "content_2")},
                weights={"semantic": SEMANTIC_WEIGHT, "keyword": KEYWORD_WEIGHT,
                    "source": SOURCE_TYPE_WEIGHT, "balance": SLOT_BALANCE_WEIGHT}) if evidence_search else None,
            project_id=project_id,
            query=query,
            retrieval_mode=mode,
            retrieval_run_id=run_id,
            retrieval_latency_ms=duration_ms,
            evidence_limitations=(
                (["Relevance scores rank source passages; they are not answer confidence or proof of support."] if evidence_search else [])
                + (["Some vector matches were excluded because source identity, revision or embedding compatibility could not be verified."] if rejected_matches else [])
                +
                (["Whole segments crossing the requested verbal window are excluded; word-level clipping is unavailable."] if window_seconds is not None else [])
                + (["Legacy chunks lack current-policy validation; use explicit project refresh before treating their provenance as validated."] if any(r.evidence_revision is None for r in results) else [])
            ),
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


def _evidence_snapshot(records: list[dict[str, Any]]) -> str:
    return hash_payload(sorted((str(r.get("chunk_id")), hash_payload(r)) for r in records))


def _validated_vector_matches(project_id, records, matches, settings):
    """Bind vector hits to the stored source; never display orphan/stale payload text."""
    by_id = {r.get("chunk_id"): r for r in records if r.get("chunk_id")}
    valid = []
    for match in matches:
        payload = match.get("payload")
        if not isinstance(payload, dict):
            continue
        record = by_id.get(payload.get("chunk_id"))
        score = match.get("score")
        if record is None or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            continue
        if payload.get("project_id") != project_id or record.get("project_id") != project_id:
            continue
        if any(payload.get(key) != record.get(key) for key in
            ("content_id", "slot", "platform", "source_type", "evidence_revision", "content_hash", "text", "start_time", "end_time")):
            continue
        if any(row.get("embedding_model_name") != settings.embedding_model_name or
               row.get("embedding_model_version") != settings.embedding_model_version for row in (record, payload)):
            continue
        valid.append(match)
    return valid


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
        evidence_revision=candidate.evidence_revision,
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
