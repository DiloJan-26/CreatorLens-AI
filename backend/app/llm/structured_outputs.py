from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator


ContentSlot: TypeAlias = Literal["content_1", "content_2"]


class StructuredAnswerType(StrEnum):
    METRIC = "metric"
    COMPARISON = "comparison"
    RECOMMENDATION = "recommendation"


class EvidenceItem(BaseModel):
    citation_label: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    slot: ContentSlot | None = None
    platform: str | None = None
    source_type: str | None = None
    excerpt: str | None = None


class MetricItem(BaseModel):
    name: str = Field(min_length=1)
    slot: ContentSlot
    value: str | int | float | None = None
    availability: Literal["confirmed", "unavailable"]
    citation_label: str | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> "MetricItem":
        if self.availability == "confirmed":
            if self.value is None:
                raise ValueError("Confirmed metrics require a value.")
            if not (self.citation_label or "").strip():
                raise ValueError("Confirmed metrics require a citation label.")
        elif self.value is not None or self.citation_label is not None:
            raise ValueError(
                "Unavailable metrics cannot contain a value or citation label."
            )
        return self


class RecommendationItem(BaseModel):
    recommendation: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"] = "medium"
    citation_labels: list[str] = Field(default_factory=list)


class MetricAnswer(BaseModel):
    answer_type: Literal["metric"] = "metric"
    summary: str = Field(min_length=1)
    metrics: list[MetricItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ComparisonAnswer(BaseModel):
    answer_type: Literal["comparison"] = "comparison"
    winner: Literal[
        "content_1",
        "content_2",
        "tie",
        "insufficient_evidence",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    key_reasons: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)


class RecommendationAnswer(BaseModel):
    answer_type: Literal["recommendation"] = "recommendation"
    summary: str = Field(min_length=1)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


StructuredAnswer: TypeAlias = Annotated[
    MetricAnswer | ComparisonAnswer | RecommendationAnswer,
    Field(discriminator="answer_type"),
]


def answer_has_factual_claims(answer: StructuredAnswer) -> bool:
    if isinstance(answer, MetricAnswer):
        return any(metric.availability == "confirmed" for metric in answer.metrics)
    if isinstance(answer, ComparisonAnswer):
        return answer.winner != "insufficient_evidence" or bool(answer.key_reasons)
    return bool(answer.recommendations)

