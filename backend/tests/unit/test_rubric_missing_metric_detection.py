from app.evaluations.fixture_loader import load_project_fixtures
from app.evaluations.rubric_checks import check_missing_metric_compliance
from app.schemas.evaluation import EvaluationArtifact


def test_missing_metric_detection_rejects_numeric_value() -> None:
    fixture = load_project_fixtures()["partial_metrics_v1"]
    artifact = EvaluationArtifact(
        answer_type="metric",
        answer_text="Content 1 likes: 50.",
    )

    result = check_missing_metric_compliance(artifact, fixture)

    assert result.passed is False


def test_missing_metric_detection_accepts_unavailable_value() -> None:
    fixture = load_project_fixtures()["partial_metrics_v1"]
    artifact = EvaluationArtifact(
        answer_type="metric",
        answer_text="Content 1 confirmed likes are unavailable.",
    )

    assert check_missing_metric_compliance(artifact, fixture).passed is True
