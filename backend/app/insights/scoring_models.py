"""Versioned descriptive scoring contracts; unavailable values serialize as null."""
from typing import Literal
from pydantic import BaseModel, Field

POLICY_VERSION = "creator-insight-2.0.0"

class ScoringPolicy(BaseModel):
    version: str = POLICY_VERSION
    minimum_views: int = 1000
    performance_weights: dict[str, float] = Field(default_factory=lambda: {"reach": .5, "engagement": .5})
    overall_weights: dict[str, float] = Field(default_factory=lambda: {"public_performance": .35, "creator_efficiency": .30, "creative_structure": .25})
    calibrated: bool = False

class CreatorMetrics(BaseModel):
    platform: str
    counts: dict[str, int | None]
    rates_percent: dict[str, float | None]
    interaction_definition: list[str]
    interactions: int | None = None
    available_interactions: int | None = None
    creator_size: int | None = None
    views_per_current_creator_size: float | None = None
    interactions_per_current_creator_size: float | None = None
    publication_date: str | None = None
    observed_at: str | None = None
    age_days: float | None = None
    engagement_status: Literal["eligible", "insufficient_evidence", "not_assessable"]
    missing_inputs: list[str]
    limitations: list[str]
    provenance: dict = Field(default_factory=dict)

class ScoreComponent(BaseModel):
    feature: str
    score: float | None = Field(default=None, ge=0, le=10)
    raw_value: float | None = None
    rule: str
    weight: float = Field(default=0, ge=0)
    contribution: float | None = None
    source: str

class ScoreBreakdown(BaseModel):
    policy_version: str = POLICY_VERSION
    score: float | None = Field(default=None, ge=0, le=10)
    status: Literal["assessable", "partial", "not_assessable"] = "not_assessable"
    coverage: float = Field(default=0, ge=0, le=1)
    components: list[ScoreComponent] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rationale: str

class EvidenceAssessment(BaseModel):
    metric_completeness: float = Field(ge=0, le=1)
    transcript_status: str
    transcript_revision: str | None = None
    source_reliability: str = "unverified"
    limitations: list[str]

class CreatorScoring(BaseModel):
    policy: ScoringPolicy = Field(default_factory=ScoringPolicy)
    metrics: CreatorMetrics
    reach: ScoreBreakdown
    engagement: ScoreBreakdown
    public_performance: ScoreBreakdown
    creator_efficiency: ScoreBreakdown
    creative_structure: ScoreBreakdown
    overall: ScoreBreakdown
    evidence: EvidenceAssessment
    comparison_signature: list[str]
    authoritative_winner: None = None
