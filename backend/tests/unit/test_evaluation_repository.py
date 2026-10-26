from sqlalchemy.orm import Session

from app.db.repositories.evaluation_repository import EvaluationRepository
from app.schemas.evaluation import EvaluationCaseDefinition


def _case_definition() -> EvaluationCaseDefinition:
    return EvaluationCaseDefinition.model_validate(
        {
            "case_id": "comparison_repository_001",
            "project_fixture": "complete_comparison_v1",
            "question": "Which content performed better?",
            "expected_answer_type": "comparison",
            "required_sources": ["metadata"],
            "forbidden_claims": ["invented views"],
            "rubric": {
                "must_compare_both_contents": True,
                "must_cite_evidence": True,
                "must_not_estimate_missing_metrics": True,
                "must_report_limitations": True,
            },
        }
    )


def test_evaluation_repository_records_dataset_case_and_result(
    db_session: Session,
) -> None:
    repository = EvaluationRepository(db_session)
    dataset = repository.create_dataset(
        name="creatorlens_core",
        version="1.0.0",
        source_path="app/evaluations/datasets/creatorlens_core_v1.jsonl",
        description="Core regression dataset",
    )
    evaluation_case = repository.add_case(dataset.id, _case_definition())
    run = repository.start_run(
        dataset_id=dataset.id,
        evaluator="deterministic",
        total_cases=1,
    )
    result = repository.record_result(
        run_id=run.id,
        evaluation_case_id=evaluation_case.id,
        status="PASSED",
        answer_type="comparison",
        answer_text="Content 1 has the stronger confirmed result.",
        citation_labels=["Content 1 · YouTube · metadata"],
        metric_scores={"citation_presence": 1.0},
        rubric_results={"must_cite_evidence": True},
        duration_ms=12,
    )

    assert repository.complete_run(
        run.id,
        passed_cases=1,
        failed_cases=0,
        aggregate_metrics={"pass_rate": 1.0},
    )
    assert dataset.case_count == 1
    assert repository.list_cases(dataset.id)[0].id == evaluation_case.id
    assert repository.list_results(run.id)[0].id == result.id
    assert run.status == "COMPLETED"
    assert run.aggregate_metrics == {"pass_rate": 1.0}


def test_evaluation_repository_bounds_negative_counts(db_session: Session) -> None:
    repository = EvaluationRepository(db_session)
    dataset = repository.create_dataset(
        name="bounded_counts",
        version="1.0.0",
        source_path="dataset.jsonl",
    )
    run = repository.start_run(
        dataset_id=dataset.id,
        evaluator="deterministic",
        total_cases=-1,
    )

    assert run.total_cases == 0
    assert repository.complete_run(
        run.id,
        passed_cases=-1,
        failed_cases=-1,
        aggregate_metrics={},
    )
    assert run.passed_cases == 0
    assert run.failed_cases == 0
