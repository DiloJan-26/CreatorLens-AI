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
    project_id: str | None,
    llm_provider: str,
    llm_model: str,
    usage: TokenUsage,
    estimated_cost_usd: Decimal | None = None,
    pricing_source: str | None = None,
    provider_invocation_count: int | None = None,
    inference_at=None,
) -> bool:
    if llm_run_id is None or not is_database_configured():
        return False
    try:
        details=None
        if provider_invocation_count is not None:
            from app.llm.cost_estimation import estimate_model_cost
            from app.core.config import get_settings
            settings=get_settings()
            usage=usage or TokenUsage()
            model=usage.model_id or llm_model
            details=estimate_model_cost(usage,provider=llm_provider,model=model,
                service_tier=usage.service_tier or settings.llm_estimate_service_tier,
                caching_mode=settings.llm_cache_billing_mode,deterministic=provider_invocation_count==0,at=inference_at)
            if provider_invocation_count and (inference_at is None or getattr(inference_at,'tzinfo',None) is None):
                details.update(status='pricing_unavailable',estimated_cost_usd=None,priced_subtotal_usd=None,components={},
                    reason='Actual timezone-aware inference timestamp unavailable; no current-date repricing.')
            details.update(requested_model=llm_model, observed_model=usage.model_id,
                model_identity_status='reported' if usage.model_id else 'unreported')
            if inference_at is not None: details['inference_started_at']=inference_at.isoformat()
            estimated_cost_usd=details['estimated_cost_usd'];pricing_source=details.get('policy_version');llm_model=model
        with database_session() as session:
            CostRepository(session).record(
                llm_run_id=llm_run_id,
                project_id=project_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                usage=usage,
                estimated_cost_usd=estimated_cost_usd,
                pricing_source=pricing_source, estimate_details=details,
                event_key=(llm_run_id+":inference") if details is not None else None,
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
        from app.llm.operation_analytics import operation_analytics
        analytics=operation_analytics(session,project_id)
        runs = LlmRunRepository(session).list_recent(
            project_id=project_id,
            limit=limit,
        )
        # One scoped query for the displayed run cost breakdowns; no inference.
        from sqlalchemy import select
        from app.db.models.llm_observability import CostEvent
        events=session.scalars(select(CostEvent).where(CostEvent.llm_run_id.in_([r['id'] for r in runs]))).all() if runs else []
        by_run={}
        for event in events: by_run.setdefault(event.llm_run_id,[]).append(CostRepository.to_record(event))
        for run in runs: run['cost_events']=by_run.get(run['id'],[])
    return CostMetricsResponse(
        project_id=project_id,
        totals=CostTotals(**totals), analytics=analytics,
        runs=[LlmRunSummary(**run) for run in runs],
    )


def annotate_operation(run_id, **details):
    """Best-effort finish metadata without overwriting completed/failed status."""
    if run_id is None or not is_database_configured():return False
    try:
        with database_session() as session:
            from app.db.models.llm_observability import LlmRun
            run=session.get(LlmRun,run_id)
            if run is None:return False
            LlmRunRepository._apply_observability(run,**details)
        return True
    except Exception:
        logger.warning('Operation telemetry update failed.')
        return False



def intelligence_policy_metadata(context):
    """Allowlisted version strings only; no prompts, transcripts or user data."""
    context=context or {};summary=context.get('summary') or {};decision=summary.get('goal_comparison') or {}
    versions={'context':context.get('policy_version'),'comparison':decision.get('decision_policy_version'),
        'metrics':decision.get('metric_policy_version'),'creative':decision.get('creative_policy_version'),
        'recommendations':(summary.get('creator_recommendations') or {}).get('policy_version')}
    return {'operation_version':'1.0.0','policy_versions':{k:v for k,v in versions.items() if isinstance(v,str)}}
