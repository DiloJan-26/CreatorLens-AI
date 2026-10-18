from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
)
from app.db.repositories._utils import utc_now
from app.schemas.evaluation import EvaluationCaseDefinition


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_dataset(
        self,
        *,
        name: str,
        version: str,
        source_path: str,
        description: str | None = None,
    ) -> EvaluationDataset:
        timestamp = utc_now()
        dataset = EvaluationDataset(
            id=str(uuid4()),
            name=name,
            version=version,
            description=description,
            source_path=source_path,
            case_count=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def add_case(
        self,
        dataset_id: str,
        definition: EvaluationCaseDefinition,
    ) -> EvaluationCase:
        dataset = self.session.get(EvaluationDataset, dataset_id)
        if dataset is None:
            raise ValueError("Evaluation dataset does not exist.")

        evaluation_case = EvaluationCase(
            id=str(uuid4()),
            dataset_id=dataset_id,
            case_key=definition.case_id,
            project_fixture=definition.project_fixture,
            question=definition.question,
            expected_answer_type=definition.expected_answer_type,
            required_sources=list(definition.required_sources),
            forbidden_claims=list(definition.forbidden_claims),
            rubric=definition.rubric.model_dump(),
            created_at=utc_now(),
        )
        self.session.add(evaluation_case)
        dataset.case_count += 1
        dataset.updated_at = utc_now()
        self.session.flush()
        return evaluation_case

    def start_run(
        self,
        *,
        dataset_id: str,
        evaluator: str,
        total_cases: int,
        model_name: str | None = None,
    ) -> EvaluationRun:
        run = EvaluationRun(
            id=str(uuid4()),
            dataset_id=dataset_id,
            status="RUNNING",
            evaluator=evaluator,
            model_name=model_name,
            total_cases=max(total_cases, 0),
            passed_cases=0,
            failed_cases=0,
            aggregate_metrics={},
            error_code=None,
            created_at=utc_now(),
            completed_at=None,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def record_result(
        self,
        *,
        run_id: str,
        evaluation_case_id: str,
        status: str,
        answer_type: str | None = None,
        answer_text: str | None = None,
        citation_labels: list[str] | None = None,
        metric_scores: dict[str, Any] | None = None,
        rubric_results: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> EvaluationResult:
        result = EvaluationResult(
            id=str(uuid4()),
            run_id=run_id,
            evaluation_case_id=evaluation_case_id,
            status=status,
            answer_type=answer_type,
            answer_text=answer_text,
            citation_labels=list(citation_labels or []),
            metric_scores=dict(metric_scores or {}),
            rubric_results=dict(rubric_results or {}),
            duration_ms=max(duration_ms, 0) if duration_ms is not None else None,
            error_code=error_code[:64] if error_code else None,
            created_at=utc_now(),
        )
        self.session.add(result)
        self.session.flush()
        return result

    def complete_run(
        self,
        run_id: str,
        *,
        passed_cases: int,
        failed_cases: int,
        aggregate_metrics: dict[str, Any],
    ) -> bool:
        run = self.session.get(EvaluationRun, run_id)
        if run is None:
            return False
        run.status = "COMPLETED"
        run.passed_cases = max(passed_cases, 0)
        run.failed_cases = max(failed_cases, 0)
        run.aggregate_metrics = dict(aggregate_metrics)
        run.error_code = None
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def fail_run(self, run_id: str, *, error_code: str) -> bool:
        run = self.session.get(EvaluationRun, run_id)
        if run is None:
            return False
        run.status = "FAILED"
        run.error_code = error_code[:64]
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def list_cases(self, dataset_id: str) -> list[EvaluationCase]:
        return list(
            self.session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.dataset_id == dataset_id)
                .order_by(EvaluationCase.case_key)
            ).all()
        )

    def list_results(self, run_id: str) -> list[EvaluationResult]:
        return list(
            self.session.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.run_id == run_id)
                .order_by(EvaluationResult.created_at)
            ).all()
        )
