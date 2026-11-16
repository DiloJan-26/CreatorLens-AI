from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, case, or_, cast, Numeric
from sqlalchemy.orm import Session

from app.db.models.llm_observability import CostEvent, LlmRun
from app.db.repositories._utils import utc_now
from app.llm.token_usage import TokenUsage


class CostRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        llm_run_id: str,
        project_id: str | None,
        llm_provider: str,
        llm_model: str,
        usage: TokenUsage | None,
        estimated_cost_usd: Decimal | str | float | None,
        pricing_source: str | None = None, estimate_details: dict | None = None, event_key: str | None = None,
    ) -> CostEvent:
        if event_key:
            previous=self.session.scalar(select(CostEvent).where(CostEvent.event_key==event_key))
            if previous is not None: return previous
        event = CostEvent(
            id=str(uuid4()), estimate_details=estimate_details, event_key=event_key,
            priced_subtotal_usd=_optional_cost((estimate_details or {}).get("priced_subtotal_usd")),cost_status=(estimate_details or {}).get("status"),
            llm_run_id=llm_run_id,
            project_id=project_id,
            llm_provider=_required_text(llm_provider, 32),
            llm_model=_required_text(llm_model, 128),
            input_tokens=_usage_count(usage, "input_tokens"),
            output_tokens=_usage_count(usage, "output_tokens"),
            total_tokens=_usage_count(usage, "total_tokens"),
            estimated_cost_usd=_optional_cost(estimated_cost_usd),
            pricing_source=_optional_text(pricing_source, 128),
            created_at=utc_now(),
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_run(self, llm_run_id: str) -> list[dict[str, Any]]:
        events = self.session.scalars(
            select(CostEvent)
            .where(CostEvent.llm_run_id == llm_run_id)
            .order_by(CostEvent.created_at)
        ).all()
        return [self.to_record(event) for event in events]

    def list_for_project(
        self,
        project_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        events = self.session.scalars(
            select(CostEvent)
            .where(CostEvent.project_id == project_id)
            .order_by(CostEvent.created_at.desc())
            .limit(max(1, min(limit, 500)))
        ).all()
        return [self.to_record(event) for event in events]

    def summary(self, *, project_id: str | None = None) -> dict[str, Any]:
        # Aggregate the entire scope, independently of paginated history.
        runtime=or_(LlmRun.execution_mode.is_(None),LlmRun.execution_mode=='runtime')
        events=select(func.count(CostEvent.id),func.sum(CostEvent.input_tokens),func.sum(CostEvent.output_tokens),
            func.sum(CostEvent.total_tokens),func.sum(exact_cost_expression())).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(runtime)
        if project_id is not None: events=events.where(CostEvent.project_id==project_id)
        row=self.session.execute(events).one()
        inference=runtime & or_(LlmRun.provider_invocation_count>0,
            (LlmRun.provider_invocation_count.is_(None)) & (LlmRun.llm_provider!='internal'))
        runs=select(func.count(LlmRun.id),func.sum(LlmRun.provider_invocation_count),
            func.sum(case((inference,1),else_=0)),
            func.sum(case(((LlmRun.llm_provider=='internal') & (LlmRun.llm_model=='deterministic_metric_answer'),1),else_=0)),
            func.sum(case((LlmRun.provider_invocation_count.is_(None),1),else_=0))).where(runtime)
        priced=select(func.count(CostEvent.id)).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(inference,CostEvent.estimated_cost_usd.is_not(None))
        zero=select(func.count(CostEvent.id)).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(runtime,LlmRun.llm_provider=='internal',CostEvent.estimated_cost_usd==0)
        if project_id is not None:
            runs=runs.where(LlmRun.project_id==project_id);priced=priced.where(LlmRun.project_id==project_id);zero=zero.where(LlmRun.project_id==project_id)
        legacy_prices=select(func.count(CostEvent.id)).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(inference,CostEvent.estimated_cost_usd.is_not(None),CostEvent.cost_status.is_(None))
        if project_id is not None:legacy_prices=legacy_prices.where(LlmRun.project_id==project_id)
        legacy_estimates=int(self.session.scalar(legacy_prices) or 0)
        operations,invocations,inference_events,deterministic,legacy=self.session.execute(runs).one()
        measured=select(func.count(CostEvent.id)).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(inference)
        missing=select(func.count(LlmRun.id)).outerjoin(CostEvent,CostEvent.llm_run_id==LlmRun.id).where(inference,CostEvent.id.is_(None))
        if project_id is not None:
            measured=measured.where(LlmRun.project_id==project_id);missing=missing.where(LlmRun.project_id==project_id)
        inference_events=int(self.session.scalar(measured) or 0)+int(self.session.scalar(missing) or 0)
        known=int(self.session.scalar(priced) or 0);unknown=max(0,inference_events-known)
        partial_sum=select(func.sum(exact_cost_expression(subtotal=True))).join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(inference)
        if project_id is not None:partial_sum=partial_sum.where(LlmRun.project_id==project_id)
        inference_subtotal=self.session.scalar(partial_sum)
        subtotal=row[4]
        status='partial' if unknown and inference_subtotal is not None else 'partial' if unknown and known else 'unavailable' if unknown else 'complete' if row[0] else 'not_measured'
        if status=='complete' and legacy_estimates:status='legacy_unverified'
        return dict(event_count=int(row[0]),input_tokens=int(row[1]) if row[1] is not None else (0 if not row[0] else None),
            output_tokens=int(row[2]) if row[2] is not None else (0 if not row[0] else None),total_tokens=int(row[3]) if row[3] is not None else (0 if not row[0] else None),
            estimated_cost_usd=subtotal if not unknown else None,priced_subtotal_usd=inference_subtotal if inference_events else subtotal,
            total_operations=int(operations),model_invocations=int(invocations or 0),inference_events=inference_events,
            priced_inference_events=known,unpriced_inference_events=unknown,deterministic_operations=int(deterministic or 0),
            known_zero_events=int(self.session.scalar(zero) or 0),legacy_invocation_unknown=int(legacy or 0),
            pricing_coverage=known/inference_events if inference_events else None,legacy_estimate_events=legacy_estimates,
            verified_pricing_coverage=(known-legacy_estimates)/inference_events if inference_events else None,cost_status=status,
            actual_billed_cost_usd=None)

    @staticmethod
    def to_record(event: CostEvent) -> dict[str, Any]:
        result={column.name:getattr(event,column.name) for column in event.__table__.columns}
        details=event.estimate_details or {}
        for name in ('estimated_cost_usd','priced_subtotal_usd'):
            if details.get(name) is not None:result[name]=Decimal(details[name])
        return result


def _optional_cost(value: Decimal | str | float | None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not cost.is_finite() or cost < 0:
        return None
    try:
        return cost.quantize(Decimal("0.00000001"))
    except InvalidOperation:
        return None


def _usage_count(usage: TokenUsage | None, field: str) -> int | None:
    if usage is None:
        return None
    value = getattr(usage, field)
    return max(value, 0) if value is not None else None


def _required_text(value: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Required cost metadata cannot be empty.")
    return normalized[:limit]


def _optional_text(value: str | None, limit: int) -> str | None:
    normalized = (value or "").strip()
    return normalized[:limit] if normalized else None


def exact_cost_expression(*,subtotal=False):
    """New estimates retain sub-cent precision in existing JSON; legacy columns stay untouched."""
    name='priced_subtotal_usd' if subtotal else 'estimated_cost_usd'
    stored=cast(CostEvent.estimate_details[name].as_string(),Numeric(24,12))
    legacy=func.coalesce(CostEvent.priced_subtotal_usd,CostEvent.estimated_cost_usd) if subtotal else CostEvent.estimated_cost_usd
    return func.coalesce(stored,legacy)
