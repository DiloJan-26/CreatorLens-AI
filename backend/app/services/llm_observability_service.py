from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import Any

from app.db.repositories.cost_repository import CostRepository
from app.db.repositories.llm_run_repository import LlmRunRepository
from app.db.session import database_session, is_database_configured
from app.llm.token_usage import TokenUsage
from app.schemas.cost import CostMetricsResponse, CostTotals, LlmRunSummary
from app.services.storage_compat_service import get_project_detail_record


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectRuntimeSignals:
    cache_hit: bool | None
    cache_miss: bool | None
    transcript_provider: str | None
    transcript_fallback_used: bool | None
    embedding_reused: bool | None


def get_project_runtime_signals(project_id: str) -> ProjectRuntimeSignals:
    try:
        project = get_project_detail_record(project_id) or {}
    except Exception:
        logger.exception(
            "Could not load project runtime signals project_id=%s",
            project_id,
        )
        return ProjectRuntimeSignals(None, None, None, None, None)
    items = [
        item
        for item in project.get("content_items", [])
        if isinstance(item, dict)
    ]
    extraction_values = _known_bools(items, "last_extraction_cache_hit")
    embedding_values = _known_bools(items, "last_embedding_reused")
    providers = sorted(
        {
            str(item.get("transcript_source")).strip()
            for item in items
            if str(item.get("transcript_source") or "").strip()
            not in {"", "unavailable", "None"}
        }
    )
    fallback_sources = {
        "deepgram_multilingual",
        "apify_youtube_transcript",
        "supadata_platform_captions",
        "supadata_generated_transcript",
        "assemblyai",
    }
    cache_hit = all(extraction_values) if extraction_values else None
    cache_miss = any(not value for value in extraction_values) if extraction_values else None
    fallback_used = (
        any(provider in fallback_sources for provider in providers)
        if providers
        else None
    )
    return ProjectRuntimeSignals(
        cache_hit=cache_hit,
        cache_miss=cache_miss,
        transcript_provider=",".join(providers)[:64] or None,
        transcript_fallback_used=fallback_used,
        embedding_reused=(all(embedding_values) if embedding_values else None),
    )


def _known_bools(items: list[dict[str, Any]], field: str) -> list[bool]:
    return [item[field] for item in items if isinstance(item.get(field), bool)]


def start_llm_run(**kwargs: Any) -> str | None:
    if not is_database_configured():
        return None
    try:
        with database_session() as session:
            return LlmRunRepository(session).start(**kwargs).id
    except Exception:
        logger.exception("Could not start LLM observability run.")
        return None


def complete_llm_run(run_id: str | None, **kwargs: Any) -> bool:
    if run_id is None or not is_database_configured():
        return False
    try:
        with database_session() as session:
            return LlmRunRepository(session).complete(run_id, **kwargs)
    except Exception:
        logger.exception("Could not complete LLM observability run run_id=%s", run_id)
        return False


def fail_llm_run(run_id: str | None, *, error_code: str, **kwargs: Any) -> bool:
    if run_id is None or not is_database_configured():
        return False
    try:
        with database_session() as session:
            return LlmRunRepository(session).fail(
                run_id,
                error_code=error_code,
                **kwargs,
            )
    except Exception:
        logger.exception("Could not fail LLM observability run run_id=%s", run_id)
        return False


def record_cost_event(
    *,
    llm_run_id: str | None,
    project_id: str,
    llm_provider: str,
    llm_model: str,
    usage: TokenUsage,
    estimated_cost_usd: Decimal | None,
    pricing_source: str | None,
) -> bool:
    if llm_run_id is None or not is_database_configured():
        return False
    try:
        with database_session() as session:
            CostRepository(session).record(
                llm_run_id=llm_run_id,
                project_id=project_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                usage=usage,
                estimated_cost_usd=estimated_cost_usd,
                pricing_source=pricing_source,
            )
        return True
    except Exception:
        logger.exception("Could not record cost event llm_run_id=%s", llm_run_id)
        return False


def get_cost_metrics(
    *,
    project_id: str | None = None,
    limit: int = 50,
) -> CostMetricsResponse:
    if not is_database_configured():
        return CostMetricsResponse(
            project_id=project_id,
            totals=CostTotals(),
            runs=[],
        )
    with database_session() as session:
        totals = CostRepository(session).summary(project_id=project_id)
        runs = LlmRunRepository(session).list_recent(
            project_id=project_id,
            limit=limit,
        )
    return CostMetricsResponse(
        project_id=project_id,
        totals=CostTotals(**totals),
        runs=[LlmRunSummary(**run) for run in runs],
    )
