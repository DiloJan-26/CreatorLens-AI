"""Strict semantic labels and source-bound evidence. No model-generated scores."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "creative-features-1.0.0"
PROMPT_VERSION = "1.0.0"
CREATIVE_POLICY = "semantic-creative-1.0.0"
FEATURES = ("opening_type", "verbal_hook_clarity", "topic_specificity", "curiosity_gap",
    "audience_benefit", "problem_solution_clarity", "audience_specificity", "spoken_cta", "description_cta", "evidence_coverage")
OPENING_LABELS = {"question", "problem", "curiosity", "introduction", "story", "other", "unassessable"}
LABELS = {"clear", "partial", "absent", "unassessable"}

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class SemanticEvidence(StrictModel):
    id: str
    project_id: str
    content_id: str
    slot: Literal["content_1", "content_2"]
    platform: str
    source_type: Literal["opening", "transcript", "description"]
    text: str = Field(min_length=1, max_length=2400)
    start_time: float | None = None
    end_time: float | None = None

class EvidenceReference(StrictModel):
    evidence_id: str
    content_id: str
    slot: Literal["content_1", "content_2"]
    excerpt: str = Field(min_length=1, max_length=600)
    start_time: float | None = None
    end_time: float | None = None

class SemanticFeature(StrictModel):
    feature: Literal["opening_type", "verbal_hook_clarity", "topic_specificity", "curiosity_gap", "audience_benefit", "problem_solution_clarity", "audience_specificity", "spoken_cta", "description_cta", "evidence_coverage"]
    value: Literal["question", "problem", "curiosity", "introduction", "story", "other", "clear", "partial", "absent", "unassessable"]
    status: Literal["assessed", "unassessable"]
    evidence: list[EvidenceReference] = Field(max_length=3)

class CreativeFeatures(StrictModel):
    schema_version: Literal["creative-features-1.0.0"]
    project_id: str
    content_id: str
    slot: Literal["content_1", "content_2"]
    input_revision: str
    features: list[SemanticFeature] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def exact_features(self):
        if set(f.feature for f in self.features) != set(FEATURES):
            raise ValueError("Exactly the ten defined features are required.")
        for f in self.features:
            if f.value not in (OPENING_LABELS if f.feature == "opening_type" else LABELS):
                raise ValueError("Unsupported classification.")
            if (f.status == "unassessable") != (f.value == "unassessable"):
                raise ValueError("Missing evidence cannot be a negative classification.")
            if f.status == "assessed" and not f.evidence:
                raise ValueError("Assessed features require evidence.")
        return self
