from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


AnswerType = Literal["metric", "comparison", "recommendation"]
EvidenceSourceType = Literal["metadata", "description", "hook", "transcript"]


class EvaluationRubric(BaseModel):
    must_compare_both_contents: bool = False
    must_cite_evidence: bool = True
    must_not_estimate_missing_metrics: bool = True
    must_report_limitations: bool = True
    minimum_faithfulness: float = Field(default=0.25, ge=0.0, le=1.0)
    minimum_response_relevance: float = Field(default=0.8, ge=0.0, le=1.0)
    minimum_context_relevance: float = Field(default=0.8, ge=0.0, le=1.0)


class EvaluationCaseDefinition(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]+$")
    project_fixture: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_answer_type: AnswerType
    required_sources: list[EvidenceSourceType] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_answer_terms: list[str] = Field(default_factory=list)
    rubric: EvaluationRubric

    @model_validator(mode="after")
    def comparison_requires_both_contents(self) -> "EvaluationCaseDefinition":
        if (
            self.expected_answer_type == "comparison"
            and not self.rubric.must_compare_both_contents
        ):
            raise ValueError("Comparison cases must require both content items.")
        return self


class EvaluationFixtureContent(BaseModel):
    slot: Literal["content_1", "content_2"]
    platform: Literal["youtube", "instagram", "facebook"]
    title: str
    description: str | None = None
    creator: str
    metadata: dict[str, Any]
    transcript_available: bool
    transcript_segments: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def transcript_state_is_consistent(self) -> "EvaluationFixtureContent":
        if not self.transcript_available and self.transcript_segments:
            raise ValueError(
                "Unavailable transcripts cannot contain transcript segments."
            )
        return self


class EvaluationProjectFixture(BaseModel):
    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]+$")
    description: str = Field(min_length=1)
    contents: list[EvaluationFixtureContent] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def contains_both_slots(self) -> "EvaluationProjectFixture":
        if {content.slot for content in self.contents} != {
            "content_1",
            "content_2",
        }:
            raise ValueError("Project fixtures must contain both content slots.")
        return self


class EvaluationFixtureCollection(BaseModel):
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    fixtures: list[EvaluationProjectFixture] = Field(min_length=1)

    @model_validator(mode="after")
    def fixture_ids_are_unique(self) -> "EvaluationFixtureCollection":
        fixture_ids = [fixture.fixture_id for fixture in self.fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("Fixture IDs must be unique.")
        return self


class EvaluationEvidence(BaseModel):
    citation_label: str = Field(min_length=1)
    slot: Literal["content_1", "content_2"]
    platform: str = Field(min_length=1)
    source_type: EvidenceSourceType
    text: str = Field(min_length=1)


class EvaluationArtifact(BaseModel):
    answer_type: AnswerType
    answer_text: str = Field(min_length=1)
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @property
    def citation_labels(self) -> list[str]:
        return [item.citation_label for item in self.evidence]

    @property
    def retrieved_contexts(self) -> list[str]:
        return [item.text for item in self.evidence]


class EvaluationCheckResult(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    message: str


class EvaluationCaseReport(BaseModel):
    case_id: str
    status: Literal["PASSED", "FAILED"]
    answer_type: AnswerType
    answer_text: str
    citation_labels: list[str] = Field(default_factory=list)
    metric_scores: dict[str, float] = Field(default_factory=dict)
    rubric_results: dict[str, EvaluationCheckResult] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)


class EvaluationRunReport(BaseModel):
    run_id: str
    dataset: str
    evaluator: str
    status: Literal["COMPLETED", "FAILED"]
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    aggregate_metrics: dict[str, float] = Field(default_factory=dict)
    cases: list[EvaluationCaseReport] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    persisted: bool = False


class EvaluationRunRequest(BaseModel):
    dataset: str = Field(
        default="creatorlens_core_v1",
        pattern=r"^[a-z0-9][a-z0-9_]+$",
    )


class EvaluationDatasetSummary(BaseModel):
    name: str
    version: str
    case_count: int = Field(ge=0)
    answer_types: list[AnswerType]


class EvaluationRunSummary(BaseModel):
    id: str
    dataset_name: str
    dataset_version: str
    status: str
    evaluator: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    aggregate_metrics: dict[str, Any]
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvaluationResultSummary(BaseModel):
    case_id: str
    status: str
    answer_type: str | None = None
    citation_labels: list[str]
    metric_scores: dict[str, Any]
    rubric_results: dict[str, Any]
    duration_ms: int | None = None
    error_code: str | None = None


class EvaluationRunDetail(BaseModel):
    run: EvaluationRunSummary
    results: list[EvaluationResultSummary]
