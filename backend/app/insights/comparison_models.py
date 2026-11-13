"""Canonical, versioned objective decisions. No statistical confidence field."""
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class ComparisonObjective(str, Enum):
    BALANCED = 'balanced'
    REACH = 'reach'
    ENGAGEMENT = 'engagement'
    CREATIVE_QUALITY = 'creative_quality'

class DecisionOutcome(str, Enum):
    CONTENT_1 = 'content_1'
    CONTENT_2 = 'content_2'
    TIE = 'tie'
    INSUFFICIENT = 'insufficient_evidence'
    INCOMPARABLE = 'incomparable'

class ComparisonPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    version: Literal['goal-comparison-1.0.0'] = 'goal-comparison-1.0.0'
    engagement_tie_percentage_points: float = .10
    score_tie_points: float = .50
    reach_tie_views: int = 0
    minimum_engagement_views: int = 1000
    calibrated: bool = False

class ComparisonEligibility(BaseModel):
    status: Literal['eligible', 'insufficient_evidence', 'incomparable']
    reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)

class ComparisonIdentity(BaseModel):
    slot: Literal['content_1','content_2']
    content_id: str | None = None
    project_id: str
    platform: str | None = None
    ownership_source: str
    metric_provenance: dict = Field(default_factory=dict)
    metric_input_revision: str
    transcript_revision: str | None = None
    semantic_snapshot_id: str | None = None
    semantic_input_revision: str | None = None
    publication_date: str | None = None
    observed_at: str | None = None
    age_days: float | None = None

class DimensionLeader(BaseModel):
    dimension: str
    metric: str
    interpretation: Literal['descriptive','heuristic']
    eligibility: ComparisonEligibility
    outcome: DecisionOutcome
    winner_slot: Literal['content_1','content_2'] | None = None
    winner_content_id: str | None = None
    descriptive_leader_slot: Literal['content_1','content_2'] | None = None
    values: dict[str, int | float | None]
    difference_content_1_minus_content_2: int | float | None = None
    units: str
    difference_units: Literal['views','percentage_points','score_points']
    tie_tolerance: float
    contributions: dict[str, list[dict]] = Field(default_factory=dict)
    feature_differences: list[dict] = Field(default_factory=list)
    evidence_references: dict[str, list[dict]] = Field(default_factory=dict)
    explanation: str
    limitations: list[str] = Field(default_factory=list)

class ComparisonDecision(BaseModel):
    project_id: str
    selected_objective: ComparisonObjective
    policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)
    decision_policy_version: str = 'goal-comparison-1.0.0'
    metric_policy_version: str
    creative_policy_version: str | None = None
    content_1: ComparisonIdentity
    content_2: ComparisonIdentity
    eligibility: ComparisonEligibility
    outcome: DecisionOutcome
    winner_slot: Literal['content_1','content_2'] | None = None
    winner_content_id: str | None = None
    objective_units: str
    difference_content_1_minus_content_2: int | float | None = None
    difference_units: str
    raw_objective_values: dict[str, int | float | None]
    eligible_scoring_inputs: dict[str, list[str]]
    key_contributions: dict[str, list[dict]]
    explanation: str
    missing_evidence: list[str]
    limitations: list[str]
    objective_decisions: dict[ComparisonObjective, DimensionLeader]
    dimension_leaders: dict[str, DimensionLeader]
