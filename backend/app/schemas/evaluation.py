from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


AnswerType = Literal["metric", "comparison", "recommendation"]
EvidenceSourceType = Literal["metadata", "description", "hook", "transcript"]


class EvaluationRubric(BaseModel):
    must_compare_both_contents: bool = False
    must_cite_evidence: bool = True
    must_not_estimate_missing_metrics: bool = True
    must_report_limitations: bool = True


class EvaluationCaseDefinition(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]+$")
    project_fixture: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_answer_type: AnswerType
    required_sources: list[EvidenceSourceType] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
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
