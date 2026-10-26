from copy import deepcopy
from typing import Any

from app.insights import insight_service


def _configure_fixture(
    monkeypatch,
    comparison_project_fixture: dict[str, object],
) -> None:
    project = comparison_project_fixture["project"]
    transcripts = comparison_project_fixture["transcripts"]
    assert isinstance(project, dict)
    assert isinstance(transcripts, dict)

    monkeypatch.setattr(
        insight_service,
        "get_project_detail_record",
        lambda _project_id: deepcopy(project),
    )

    def _segments(**kwargs: Any) -> list[dict[str, Any]]:
        slot = kwargs["slot"]
        value = transcripts[slot]
        assert isinstance(value, list)
        return deepcopy(value)

    monkeypatch.setattr(insight_service, "get_transcript_segments", _segments)


def test_creator_insight_summary_is_repeatable_for_same_evidence(
    monkeypatch,
    comparison_project_fixture: dict[str, object],
) -> None:
    _configure_fixture(monkeypatch, comparison_project_fixture)

    first = insight_service.get_creator_insight_summary("fixture-project")
    second = insight_service.get_creator_insight_summary("fixture-project")

    assert first.model_dump() == second.model_dump()
    assert first.content_1 is not None
    assert first.content_2 is not None
    assert first.content_1.scores.overall_score > first.content_2.scores.overall_score
    assert first.comparison.confirmed_metric_winner == "Content 1"
    assert first.comparison.overall_insight_winner == "Content 1"
    assert any("deterministic heuristics" in note for note in first.notes)


def test_metadata_completeness_does_not_override_performance_scoring(
    monkeypatch,
    comparison_project_fixture: dict[str, object],
) -> None:
    project = comparison_project_fixture["project"]
    assert isinstance(project, dict)
    content_items = project["content_items"]
    assert isinstance(content_items, list)
    content_2 = content_items[1]
    assert isinstance(content_2, dict)
    content_2["hashtags"] = []
    content_2["upload_date"] = None
    content_2["missing_fields"] = ["hashtags", "upload_date"]
    _configure_fixture(monkeypatch, comparison_project_fixture)

    summary = insight_service.get_creator_insight_summary("fixture-project")

    assert summary.content_1 is not None
    assert summary.content_2 is not None
    assert (
        summary.content_2.scores.metadata_completeness
        < summary.content_1.scores.metadata_completeness
    )
    assert summary.comparison.confirmed_metric_winner == "Content 1"
    assert "hashtags" in summary.content_2.missing_metadata
