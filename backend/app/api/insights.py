from fastapi import APIRouter, HTTPException, status

from app.insights.insight_models import CreatorInsightSummaryResponse
from app.insights.insight_service import (
    CreatorInsightProjectNotFoundError,
    get_creator_insight_summary,
)


router = APIRouter(
    prefix="/api/projects/{project_id}/insights",
    tags=["7. Creator Insights"],
)


@router.get(
    "/summary",
    response_model=CreatorInsightSummaryResponse,
    summary="Build the Creator Insight Summary",
    description=(
        "Returns deterministic comparison scores and findings used by the Insights UI. "
        "Run extraction first; verified metrics improve metric completeness."
    ),
)
def get_creator_insight_summary_endpoint(
    project_id: str,
) -> CreatorInsightSummaryResponse:
    try:
        return get_creator_insight_summary(project_id)
    except CreatorInsightProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not build Creator Insight Summary.",
        ) from None
