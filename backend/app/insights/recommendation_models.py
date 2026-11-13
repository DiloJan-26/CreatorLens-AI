"""Versioned creator actions and informational findings with explicit evidence ownership."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.insights.comparison_models import ComparisonObjective

RECOMMENDATION_POLICY = 'creator-recommendations-1.0.0'

class RecommendationEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str
    project_id: str
    content_id: str
    slot: Literal['content_1','content_2']
    platform: str
    role: Literal['target','comparison_context'] = 'target'
    source_type: Literal['opening','transcript','description','metric_snapshot']
    excerpt: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    metric_values: dict[str, int | float | None] = Field(default_factory=dict)
    metric_provenance: dict = Field(default_factory=dict)
    input_revision: str
    transcript_revision: str | None = None
    semantic_snapshot_id: str | None = None

class WeaknessSignal(BaseModel):
    rule_id: str
    feature: str
    classification: str
    observed_value: str | int | float | None
    trigger: str
    severity: int = Field(ge=0,le=3)
    observation: str

class RecommendationPriority(BaseModel):
    policy_version: str = RECOMMENDATION_POLICY
    severity: int = Field(ge=0,le=3)
    evidence_strength: int = Field(ge=0,le=2)
    objective_relevance: int = Field(ge=0,le=2)
    action_directness: int = Field(ge=0,le=1)
    score: int = Field(ge=0,le=8)
    label: Literal['high','medium','low']
    explanation: str

class CreativeExample(BaseModel):
    target_content_id: str
    method: Literal['deterministic_template'] = 'deterministic_template'
    text: str
    source_evidence_ids: list[str]
    limitation: str

class RecommendationComparison(BaseModel):
    selected_objective_status: str
    selected_outcome: str
    selected_winner_content_id: str | None = None
    dimension: str | None = None
    dimension_status: str | None = None
    dimension_outcome: str | None = None
    dimension_values: dict[str, int | float | None] = Field(default_factory=dict)

class CreatorRecommendation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    project_id: str
    target_content_id: str
    target_slot: Literal['content_1','content_2']
    target_platform: str
    selected_objective: ComparisonObjective
    policy_version: str = RECOMMENDATION_POLICY
    category: Literal['opening_hook','topic_messaging','problem_solution','cta_strategy','audience_relevance','engagement_opportunity']
    intervention_group: str
    detected_weakness: str
    observed_signal: str
    assessment_status: Literal['supported'] = 'supported'
    evidence_status: Literal['valid','partial']
    signals: list[WeaknessSignal] = Field(min_length=1)
    evidence: list[RecommendationEvidence] = Field(min_length=1)
    title: str
    recommended_change: str
    rationale: str
    experiment: str
    hypothesis: str
    limitation: str
    priority: RecommendationPriority
    basis: Literal['individual_weakness','comparative_opportunity']
    comparison: RecommendationComparison
    example: CreativeExample | None = None

class RecommendationFinding(BaseModel):
    id: str
    target_content_id: str | None = None
    target_slot: str | None = None
    category: str
    status: Literal['observed','not_assessable','incomparable']
    observation: str
    evidence: list[RecommendationEvidence] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

class CreatorRecommendationBundle(BaseModel):
    policy_version: str = RECOMMENDATION_POLICY
    project_id: str
    selected_objective: ComparisonObjective
    decision_policy_version: str
    status: Literal['ready','no_supported_actions','unavailable']
    recommendations: list[CreatorRecommendation] = Field(default_factory=list,max_length=5)
    findings: list[RecommendationFinding] = Field(default_factory=list,max_length=24)
    detected_candidates: int = 0
    merged_candidates: int = 0
    omitted_by_display_limit: int = 0
    limitations: list[str] = Field(default_factory=list)
