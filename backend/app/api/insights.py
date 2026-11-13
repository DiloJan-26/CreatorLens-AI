from fastapi import APIRouter, HTTPException, status
from app.insights.comparison_models import ComparisonObjective

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
        "Returns legacy-1.0.0 comparison fields and creator-insight-2.0.0 evidence-aware scoring objects with nullable scores. goal_comparison provides authoritative goal-comparison-1.0.0 decisions for balanced, reach, engagement or creative_quality. "
        "Run extraction first; verified metrics improve metric completeness."
    ),
)
def get_creator_insight_summary_endpoint(
    project_id: str,
    objective: ComparisonObjective = ComparisonObjective.BALANCED,
) -> CreatorInsightSummaryResponse:
    try:
        return get_creator_insight_summary(project_id, objective=objective)
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
