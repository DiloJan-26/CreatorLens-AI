from sqlalchemy.orm import Session

from app.db.models.evaluation import EvaluationDataset, EvaluationResult, EvaluationRun
from app.evaluations.regression_runner import run_regression


def test_smoke_regression_generates_and_persists_report(db_session: Session) -> None:
    report = run_regression(
        "creatorlens_ci_smoke_v1",
        session=db_session,
        persist=True,
    )

    assert report.status == "COMPLETED"
    assert report.total_cases == 5
    assert report.persisted is True
    assert report.failed_cases == 0
    assert report.aggregate_metrics["pass_rate"] == 1.0
    assert "faithfulness_lexical" in report.aggregate_metrics
    assert "response_relevance_lexical" in report.aggregate_metrics
    assert "context_relevance_lexical" in report.aggregate_metrics
    assert db_session.query(EvaluationDataset).count() == 1
    assert db_session.query(EvaluationRun).count() == 1
    assert db_session.query(EvaluationResult).count() == 5
    assert all(
        "response_relevance_quality" in case.rubric_results
        and "context_relevance_quality" in case.rubric_results
        and "faithfulness_quality" in case.rubric_results
        for case in report.cases
    )
