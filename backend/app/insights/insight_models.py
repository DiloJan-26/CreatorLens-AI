from pydantic import BaseModel, Field


class HookAnalysis(BaseModel):
    hook_text: str | None = None
    hook_type: str
    hook_score: int = Field(ge=0, le=10)
    clarity_reason: str
    detected_patterns: list[str] = Field(default_factory=list)


class InsightScores(BaseModel):
    hook_clarity: int = Field(ge=0, le=10)
    problem_solution_clarity: int = Field(ge=0, le=10)
    cta_strength: int = Field(ge=0, le=10)
    caption_strength: int = Field(ge=0, le=10)
    audience_specificity: int = Field(ge=0, le=10)
    creative_structure_score: int = Field(default=0, ge=0, le=10)
    public_performance_score: int = Field(default=0, ge=0, le=10)
    creator_efficiency_score: int = Field(default=0, ge=0, le=10)
    metadata_completeness: int = Field(ge=0, le=10)
    engagement_confidence: int = Field(ge=0, le=10)
    overall_score: int = Field(ge=0, le=10)


class ContentInsight(BaseModel):
    slot: str
    label: str
    platform: str
    title: str | None = None
    creator: str | None = None
    hook_analysis: HookAnalysis
    scores: InsightScores
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_metadata: list[str] = Field(default_factory=list)
    available_metadata: list[str] = Field(default_factory=list)
    metric_confidence_note: str
    top_improvement: str | None = None


class ComparisonInsight(BaseModel):
    confirmed_metric_winner: str | None = None
    creator_efficiency_winner: str | None = None
    creative_structure_winner: str | None = None
    hook_winner: str | None = None
    overall_insight_winner: str | None = None
    main_reason: str
    confidence_note: str
    top_recommendations: list[str] = Field(default_factory=list)
    example_rewrite_for_content_2: str | None = None


class CreatorInsightSummaryResponse(BaseModel):
    project_id: str
    content_1: ContentInsight | None = None
    content_2: ContentInsight | None = None
    comparison: ComparisonInsight
    notes: list[str] = Field(default_factory=list)
