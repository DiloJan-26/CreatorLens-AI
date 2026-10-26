import pytest

from app.evaluations.fixture_loader import (
    EvaluationFixtureError,
    list_datasets,
    load_dataset,
    load_project_fixtures,
)


def test_core_dataset_loader_returns_twenty_valid_cases() -> None:
    cases = load_dataset("creatorlens_core_v1")

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == 20
    assert all(case.project_fixture in load_project_fixtures() for case in cases)


def test_ci_smoke_dataset_is_small_and_discoverable() -> None:
    cases = load_dataset("creatorlens_ci_smoke_v1")

    assert 1 <= len(cases) <= 5
    assert "creatorlens_ci_smoke_v1" in list_datasets()


def test_dataset_loader_rejects_path_traversal() -> None:
    with pytest.raises(EvaluationFixtureError):
        load_dataset("../secrets")
