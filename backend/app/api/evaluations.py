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
from app.evaluations.publication import evaluate_and_publish, source_fingerprint, supported_datasets
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
    from app.evaluations.intelligence_models import DATASETS, DATASET_VERSION as INTELLIGENCE_VERSION, EVALUATOR
    from app.evaluations.intelligence_runner import load_intelligence_dataset
    for name in DATASETS:
        cases=load_intelligence_dataset(name)
        summaries.append(EvaluationDatasetSummary(name=name,version=INTELLIGENCE_VERSION,case_count=len(cases),answer_types=['comparison'],methodology='offline_intelligence_contracts_and_mocked_probes',evaluator=EVALUATOR))
    return summaries


@router.post(
    "/runs",
    response_model=EvaluationRunReport,
    summary="Run a deterministic regression dataset",
    description=(
        "Runs bounded, network-free RAGAS non-LLM context metrics, labelled lexical "
        "quality metrics, and DeepEval rubrics against stable fixtures, then persists "
        "the report. Intelligence v2 datasets instead exercise versioned deterministic "
        "contracts, synthetic retrieval and mocked response probes, with explicit "
        "failure/skip accounting. No Gemini quota is consumed."
    ),
)
def create_evaluation_run(payload: EvaluationRunRequest) -> EvaluationRunReport:
    if payload.dataset not in supported_datasets():
        raise HTTPException(404,"Unknown bundled evaluation dataset.")
    try:
        with database_session() as session:
            return evaluate_and_publish(payload.dataset, session=session)
    except EvaluationFixtureError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source, dataset or report changed; publication was rejected.",
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


def _bundled_run(repository, run):
    from app.evaluations.intelligence_models import DATASETS
    dataset = repository.get_dataset_by_id(run.dataset_id)
    return dataset is not None and dataset.name in set(list_datasets()) | set(DATASETS)



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
            current_source=source_fingerprint()
            return [
                _run_summary(repository, run,current_source)
                for run in repository.list_runs(limit=limit,dataset_names=supported_datasets())
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
            if run is None or not _bundled_run(repository,run):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Evaluation run not found.",
                )
            # Fetch definitions once; remote PostgreSQL must not perform one query per case.
            cases_by_id={case.id:case for case in repository.list_cases(run.dataset_id)}
            results = []
            for result in repository.list_results(run.id):
                evaluation_case = cases_by_id.get(result.evaluation_case_id)
                results.append(
                    EvaluationResultSummary(
                        scenario=evaluation_case.question if evaluation_case else None,
                        answer_text=result.answer_text,
                        case_id=evaluation_case.case_key if evaluation_case else result.evaluation_case_id,
                        status=result.status,
                        answer_type=result.answer_type,
                        citation_labels=result.citation_labels,
                        metric_scores=result.metric_scores,
                        rubric_results={k:v for k,v in result.rubric_results.items() if k!='_evaluation'},
                        evaluation_details=result.rubric_results.get('_evaluation',{}),
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


def _run_summary(repository: EvaluationRepository, run, current_source=None) -> EvaluationRunSummary:
    dataset = repository.get_dataset_by_id(run.dataset_id)
    publication=run.aggregate_metrics.get("_publication",{})
    fingerprint=publication.get("source_fingerprint")
    source_status="unverified" if not fingerprint else "current" if fingerprint==(current_source or source_fingerprint()) else "different"
    return EvaluationRunSummary(
        publication=publication,source_status=source_status,
        skipped_cases=run.aggregate_metrics.get('_evaluation',{}).get('skipped_cases',0),
        evaluation_details=run.aggregate_metrics.get('_evaluation',{}),
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
