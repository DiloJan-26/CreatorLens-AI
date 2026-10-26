from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories.cost_repository import CostRepository
from app.db.repositories.llm_run_repository import LlmRunRepository
from app.llm.token_usage import TokenUsage
from tests.unit.test_content_item_repository import _create_project


def test_cost_repository_records_known_cost(db_session: Session) -> None:
    project_id = _create_project(db_session)
    llm_run = LlmRunRepository(db_session).start(
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        prompt_name="comparison_answer",
        prompt_version="1.0.0",
    )
    repository = CostRepository(db_session)

    event = repository.record(
        llm_run_id=llm_run.id,
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        usage=TokenUsage(100, 25, 125),
        estimated_cost_usd="0.00001234",
        pricing_source="configured-model-pricing",
    )

    record = repository.list_for_run(llm_run.id)[0]
    assert record["id"] == event.id
    assert record["total_tokens"] == 125
    assert record["estimated_cost_usd"] == Decimal("0.00001234")


def test_cost_repository_keeps_unknown_cost_unavailable(db_session: Session) -> None:
    project_id = _create_project(db_session)
    llm_run = LlmRunRepository(db_session).start(
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        prompt_name="recommendation_answer",
        prompt_version="1.0.0",
    )
    repository = CostRepository(db_session)

    repository.record(
        llm_run_id=llm_run.id,
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        usage=TokenUsage(),
        estimated_cost_usd=None,
    )

    record = repository.list_for_project(project_id)[0]
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["estimated_cost_usd"] is None


def test_cost_repository_summarizes_tokens_and_known_costs(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    llm_run = LlmRunRepository(db_session).start(
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        prompt_name="comparison_answer",
        prompt_version="1.0.0",
    )
    repository = CostRepository(db_session)
    repository.record(
        llm_run_id=llm_run.id,
        project_id=project_id,
        llm_provider="gemini",
        llm_model="gemini-example",
        usage=TokenUsage(100, 25, 125),
        estimated_cost_usd="0.00001000",
    )

    summary = repository.summary(project_id=project_id)

    assert summary["event_count"] == 1
    assert summary["total_tokens"] == 125
    assert summary["estimated_cost_usd"] == Decimal("0.00001000")
