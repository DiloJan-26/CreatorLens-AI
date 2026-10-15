from fastapi import APIRouter, HTTPException, status

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


router = APIRouter(
    prefix="/api/projects/{project_id}/metrics",
    tags=["6. Verified Metrics"],
)


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
