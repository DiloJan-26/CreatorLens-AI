import json
from pathlib import Path

from app.schemas.evaluation import (
    EvaluationCaseDefinition,
    EvaluationFixtureCollection,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = (
    BACKEND_ROOT
    / "app"
    / "evaluations"
    / "datasets"
    / "creatorlens_core_v1.jsonl"
)
FIXTURE_PATH = (
    BACKEND_ROOT
    / "app"
    / "evaluations"
    / "fixtures"
    / "project_fixtures_v1.json"
)


def test_core_dataset_contains_valid_unique_cases() -> None:
    cases = [
        EvaluationCaseDefinition.model_validate_json(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.expected_answer_type for case in cases} == {
        "metric",
        "comparison",
        "recommendation",
    }


def test_dataset_cases_reference_valid_project_fixtures() -> None:
    collection = EvaluationFixtureCollection.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    fixture_ids = {fixture.fixture_id for fixture in collection.fixtures}
    cases = [
        EvaluationCaseDefinition.model_validate_json(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert fixture_ids == {
        "complete_comparison_v1",
        "partial_metrics_v1",
        "missing_transcript_v1",
    }
    assert all(case.project_fixture in fixture_ids for case in cases)


def test_missing_evidence_fixture_preserves_unavailable_values() -> None:
    collection = EvaluationFixtureCollection.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    fixture = next(
        item
        for item in collection.fixtures
        if item.fixture_id == "missing_transcript_v1"
    )
    content_2 = next(content for content in fixture.contents if content.slot == "content_2")

    assert content_2.transcript_available is False
    assert content_2.transcript_segments == []
    assert content_2.metadata["likes"] is None
    assert content_2.metadata["comments"] is None
