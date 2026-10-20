from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.llm_observability import CostEvent
from app.db.repositories._utils import utc_now
from app.llm.token_usage import TokenUsage


class CostRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        llm_run_id: str,
        project_id: str,
        llm_provider: str,
        llm_model: str,
        usage: TokenUsage | None,
        estimated_cost_usd: Decimal | str | float | None,
        pricing_source: str | None = None,
    ) -> CostEvent:
        event = CostEvent(
            id=str(uuid4()),
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
        statement = select(
            func.count(CostEvent.id),
            func.coalesce(func.sum(CostEvent.input_tokens), 0),
            func.coalesce(func.sum(CostEvent.output_tokens), 0),
            func.coalesce(func.sum(CostEvent.total_tokens), 0),
            func.sum(CostEvent.estimated_cost_usd),
        )
        if project_id is not None:
            statement = statement.where(CostEvent.project_id == project_id)
        row = self.session.execute(statement).one()
        return {
            "event_count": int(row[0] or 0),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "total_tokens": int(row[3] or 0),
            "estimated_cost_usd": row[4],
        }

    @staticmethod
    def to_record(event: CostEvent) -> dict[str, Any]:
        return {
            column.name: getattr(event, column.name)
            for column in event.__table__.columns
        }


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
