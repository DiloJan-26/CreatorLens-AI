"""Strict, versioned offline intelligence case definitions."""
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

DATASET_VERSION='2.0.0'
EVALUATOR='creatorlens-intelligence-offline-v2.0.0'
DATASETS=('creatorlens_intelligence_v2','creatorlens_intelligence_ci_v2')
CATEGORIES={'evidence_reliability','deterministic_scoring','goal_comparison','semantic_features',
    'recommendation_quality','retrieval','assistant_grounding','cross_component','semantic_reference','multilingual','live_acceptance'}

class IntelligenceCase(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id: str = Field(pattern=r'^[a-z0-9][a-z0-9_]+$')
    dataset_version: Literal['2.0.0']
    category: str
    scenario: str = Field(min_length=10)
    fixture_id: str
    operation: Literal['evidence','window','revision','scoring','comparison','semantic','recommendation','retrieval','assistant','integration','reference','stream','deferred']
    inputs: dict[str,Any] = Field(default_factory=dict)
    expected: dict[str,Any] = Field(default_factory=dict)
    execution_mode: Literal['deterministic_contract','mocked_model','synthetic_retrieval','pending_human_review','deferred_live']
    reference_basis: Literal['explicit_contract','manual_numeric_reference','agent_authored_synthetic','pending_human_review','none']
    critical: bool = False
    skip_reason: str | None = None
    references: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def consistent(self):
        if self.category not in CATEGORIES:raise ValueError('Unknown evaluation category.')
        if self.critical and self.skip_reason:raise ValueError('Critical cases cannot be pre-skipped.')
        if not self.skip_reason and not self.expected:raise ValueError('Executable cases require explicit independent expectations.')
        if self.operation=='deferred' and not self.skip_reason:raise ValueError('Deferred cases require a reason.')
        return self
