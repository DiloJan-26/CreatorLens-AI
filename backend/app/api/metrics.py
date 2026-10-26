from fastapi import APIRouter, HTTPException, Query, status

from app.models.metrics import (
    MetricSummaryResponse,
    SaveVerifiedMetricsResponse,
    VerifiedMetricInput,
)
from app.services.metric_source_service import (
    MetricProjectNotFoundError,
    MetricRecordNotFoundError,
    MetricValidationError,
    delete_verified_metric_record,
    get_metric_summary,
    save_verified_metrics_with_summary,
)
from app.schemas.cost import CostMetricsResponse
from app.services.llm_observability_service import get_cost_metrics


router = APIRouter(
    prefix="/api/projects/{project_id}/metrics",
    tags=["6. Verified Metrics"],
)

cost_router = APIRouter(
    prefix="/api/metrics",
    tags=["11. LLM Operations"],
)


@cost_router.get(
    "/cost",
    response_model=CostMetricsResponse,
    summary="Inspect LLM cost and latency telemetry",
    description=(
        "Returns persisted token, configured cost-estimate, latency, cache, "
        "retrieval, transcript, and prompt-version signals."
    ),
)
def get_cost_metrics_endpoint(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CostMetricsResponse:
    return get_cost_metrics(project_id=project_id, limit=limit)


@router.get(
    "/sources",
    response_model=MetricSummaryResponse,
    summary="Review metric sources and completeness",
    description="Shows public and user-verified metrics with provenance and missing fields.",
)
def get_metric_sources_endpoint(project_id: str) -> MetricSummaryResponse:
    try:
        return get_metric_summary(project_id)
    except MetricProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None


@router.post(
    "/verify",
    response_model=SaveVerifiedMetricsResponse,
    summary="Save user-verified metrics",
    description="Stores explicitly verified values without estimating unavailable metrics.",
)
def verify_metrics_endpoint(
    project_id: str,
    payload: VerifiedMetricInput,
) -> SaveVerifiedMetricsResponse:
    try:
        return save_verified_metrics_with_summary(project_id, payload)
    except MetricProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except MetricValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None


@router.delete(
    "/sources/{record_id}",
    summary="Delete a verified metric source",
    description="Removes one persisted metric-source record from the project.",
)
def delete_metric_source_endpoint(
    project_id: str,
    record_id: str,
) -> dict[str, str]:
    try:
        delete_verified_metric_record(project_id=project_id, record_id=record_id)
    except (MetricProjectNotFoundError, MetricRecordNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None

    return {
        "status": "deleted",
        "record_id": record_id,
    }
