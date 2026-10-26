"""Run CreatorLens evaluation datasets and persist inspectable reports."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.repositories.evaluation_repository import EvaluationRepository
from app.db.session import database_session, is_database_configured
from app.evaluations.deepeval_runner import evaluate_with_deepeval
from app.evaluations.fixture_loader import (
    DATASET_VERSION,
    DATASETS_DIR,
    build_fixture_artifact,
    build_reference_contexts,
    load_dataset,
    load_project_fixtures,
)
from app.evaluations.ragas_runner import evaluate_with_ragas
from app.schemas.evaluation import EvaluationCaseReport, EvaluationRunReport


logger = logging.getLogger(__name__)
DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[2] / "storage" / "evaluation_reports"
EVALUATOR_NAME = "ragas+deepeval-deterministic-v1.1"


def run_regression(
    dataset_name: str,
    *,
    session: Session | None = None,
    persist: bool | None = None,
) -> EvaluationRunReport:
    cases = load_dataset(dataset_name)
    fixtures = load_project_fixtures()
    should_persist = (session is not None or is_database_configured()) if persist is None else persist

    if should_persist and session is None:
        with database_session() as managed_session:
            return _run(dataset_name, cases, fixtures, managed_session)
    return _run(dataset_name, cases, fixtures, session if should_persist else None)


def _run(dataset_name, cases, fixtures, session: Session | None) -> EvaluationRunReport:
    created_at = datetime.now(UTC)
    repository = EvaluationRepository(session) if session is not None else None
    dataset_row = None
    case_rows = {}
    run_row = None

    if repository is not None:
        dataset_row = repository.get_or_create_dataset(
            name=dataset_name,
            version=DATASET_VERSION,
            source_path=str(DATASETS_DIR / f"{dataset_name}.jsonl"),
            description="CreatorLens deterministic RAG regression dataset.",
        )
        case_rows = repository.sync_cases(dataset_row.id, cases)
        run_row = repository.start_run(
            dataset_id=dataset_row.id,
            evaluator=EVALUATOR_NAME,
            total_cases=len(cases),
        )

    reports: list[EvaluationCaseReport] = []
    for case in cases:
        started = perf_counter()
        fixture = fixtures[case.project_fixture]
        artifact = build_fixture_artifact(case, fixture)
        reference_contexts = build_reference_contexts(case, fixture)
        metrics = evaluate_with_ragas(case, artifact, reference_contexts)
        checks = evaluate_with_deepeval(case, artifact, fixture, metrics)
        status = "PASSED" if all(check.passed for check in checks.values()) else "FAILED"
        report = EvaluationCaseReport(
            case_id=case.case_id,
            status=status,
            answer_type=artifact.answer_type,
            answer_text=artifact.answer_text,
            citation_labels=artifact.citation_labels,
            metric_scores=metrics,
            rubric_results=checks,
            duration_ms=max(round((perf_counter() - started) * 1000), 0),
        )
        reports.append(report)
        if repository is not None and run_row is not None:
            repository.record_result(
                run_id=run_row.id,
                evaluation_case_id=case_rows[case.case_id].id,
                status=status,
                answer_type=artifact.answer_type,
                answer_text=artifact.answer_text,
                citation_labels=artifact.citation_labels,
                metric_scores=metrics,
                rubric_results={key: value.model_dump() for key, value in checks.items()},
                duration_ms=report.duration_ms,
            )

    passed = sum(report.status == "PASSED" for report in reports)
    aggregate = _aggregate_metrics(reports)
    run_id = run_row.id if run_row is not None else str(uuid4())
    if repository is not None and run_row is not None:
        repository.complete_run(
            run_row.id,
            passed_cases=passed,
            failed_cases=len(reports) - passed,
            aggregate_metrics=aggregate,
        )

    return EvaluationRunReport(
        run_id=run_id,
        dataset=dataset_name,
        evaluator=EVALUATOR_NAME,
        status="COMPLETED",
        total_cases=len(reports),
        passed_cases=passed,
        failed_cases=len(reports) - passed,
        aggregate_metrics=aggregate,
        cases=reports,
        created_at=created_at,
        completed_at=datetime.now(UTC),
        persisted=repository is not None,
    )


def _aggregate_metrics(reports: list[EvaluationCaseReport]) -> dict[str, float]:
    if not reports:
        return {"pass_rate": 0.0}
    metric_names = sorted({name for report in reports for name in report.metric_scores})
    values = {
        name: round(sum(report.metric_scores.get(name, 0.0) for report in reports) / len(reports), 6)
        for name in metric_names
    }
    values["pass_rate"] = round(sum(report.status == "PASSED" for report in reports) / len(reports), 6)
    values["citation_presence"] = round(
        sum(bool(report.citation_labels) for report in reports) / len(reports), 6
    )
    values["missing_evidence_compliance"] = round(
        sum(
            report.rubric_results.get("missing_metric_compliance") is None
            or report.rubric_results["missing_metric_compliance"].passed
            for report in reports
        ) / len(reports),
        6,
    )
    return values


def _write_report(report: EvaluationRunReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CreatorLens RAG regression evaluation.")
    parser.add_argument("--dataset", default="creatorlens_core_v1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    report = run_regression(args.dataset, persist=False if args.no_persist else None)
    output = args.output or DEFAULT_REPORT_DIR / f"{args.dataset}_latest.json"
    _write_report(report, output)
    print(json.dumps({
        "run_id": report.run_id,
        "dataset": report.dataset,
        "status": report.status,
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "aggregate_metrics": report.aggregate_metrics,
        "persisted": report.persisted,
        "report_path": str(output),
    }, indent=2))
    return 0 if report.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
