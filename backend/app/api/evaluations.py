"""Evaluation dataset and regression-run API."""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.db.repositories.evaluation_repository import EvaluationRepository
from app.db.session import DatabaseConfigurationError, database_session
from app.evaluations.fixture_loader import (
    DATASET_VERSION,
    EvaluationFixtureError,
    list_datasets,
    load_dataset,
)
from app.evaluations.regression_runner import run_regression
from app.schemas.evaluation import (
    EvaluationDatasetSummary,
    EvaluationResultSummary,
    EvaluationRunDetail,
    EvaluationRunRequest,
    EvaluationRunReport,
    EvaluationRunSummary,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evaluations", tags=["10. RAG Evaluation"])


@router.get(
    "/datasets",
    response_model=list[EvaluationDatasetSummary],
    summary="List bundled evaluation datasets",
)
def get_evaluation_datasets() -> list[EvaluationDatasetSummary]:
    summaries = []
    for name in list_datasets():
        cases = load_dataset(name)
        summaries.append(
            EvaluationDatasetSummary(
                name=name,
                version=DATASET_VERSION,
                case_count=len(cases),
                answer_types=sorted({case.expected_answer_type for case in cases}),
            )
        )
    return summaries


@router.post(
    "/runs",
    response_model=EvaluationRunReport,
    summary="Run a deterministic regression dataset",
    description=(
        "Runs bounded, network-free RAGAS non-LLM context metrics, labelled lexical "
        "quality metrics, and DeepEval rubrics against stable fixtures, then persists "
        "the report. No Gemini quota is consumed."
    ),
)
def create_evaluation_run(payload: EvaluationRunRequest) -> EvaluationRunReport:
    try:
        with database_session() as session:
            return run_regression(payload.dataset, session=session, persist=True)
    except EvaluationFixtureError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None
    except DatabaseConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation persistence is not configured.",
        ) from None
    except Exception:
        logger.exception("Evaluation run failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation run failed.",
        ) from None


@router.get(
    "/runs",
    response_model=list[EvaluationRunSummary],
    summary="List persisted evaluation runs",
)
def get_evaluation_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[EvaluationRunSummary]:
    try:
        with database_session() as session:
            repository = EvaluationRepository(session)
            return [
                _run_summary(repository, run)
                for run in repository.list_runs(limit=limit)
            ]
    except DatabaseConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation persistence is not configured.",
        ) from None
    except Exception:
        logger.exception("Could not list evaluation runs.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load evaluation runs.",
        ) from None


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunDetail,
    summary="Inspect one persisted evaluation run",
)
def get_evaluation_run(run_id: str) -> EvaluationRunDetail:
    try:
        with database_session() as session:
            repository = EvaluationRepository(session)
            run = repository.get_run(run_id)
            if run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Evaluation run not found.",
                )
            results = []
            for result in repository.list_results(run.id):
                evaluation_case = repository.get_case_by_id(result.evaluation_case_id)
                results.append(
                    EvaluationResultSummary(
                        case_id=evaluation_case.case_key if evaluation_case else result.evaluation_case_id,
                        status=result.status,
                        answer_type=result.answer_type,
                        citation_labels=result.citation_labels,
                        metric_scores=result.metric_scores,
                        rubric_results=result.rubric_results,
                        duration_ms=result.duration_ms,
                        error_code=result.error_code,
                    )
                )
            return EvaluationRunDetail(run=_run_summary(repository, run), results=results)
    except HTTPException:
        raise
    except DatabaseConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation persistence is not configured.",
        ) from None
    except Exception:
        logger.exception("Could not load evaluation run.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load evaluation run.",
        ) from None


def _run_summary(repository: EvaluationRepository, run) -> EvaluationRunSummary:
    dataset = repository.get_dataset_by_id(run.dataset_id)
    return EvaluationRunSummary(
        id=run.id,
        dataset_name=dataset.name if dataset else "unknown",
        dataset_version=dataset.version if dataset else "unknown",
        status=run.status,
        evaluator=run.evaluator,
        total_cases=run.total_cases,
        passed_cases=run.passed_cases,
        failed_cases=run.failed_cases,
        aggregate_metrics=run.aggregate_metrics,
        error_code=run.error_code,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
