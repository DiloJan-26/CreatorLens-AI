from app.evaluations.fixture_loader import (
    build_fixture_artifact,
    build_reference_contexts,
    load_dataset,
    load_project_fixtures,
)
from app.evaluations.ragas_runner import evaluate_with_ragas
from app.evaluations.rubric_checks import evaluate_rubric


def _case(case_id: str):
    return next(
        case
        for case in load_dataset("creatorlens_core_v1")
        if case.case_id == case_id
    )


def test_metric_fixture_answer_is_question_specific() -> None:
    case = _case("metric_engagement_complete_002")
    fixture = load_project_fixtures()[case.project_fixture]

    artifact = build_fixture_artifact(case, fixture)

    assert "engagement rate" in artifact.answer_text.casefold()
    assert "7.056" in artifact.answer_text
    assert "8.293" in artifact.answer_text


def test_generic_metric_answer_fails_response_relevance_gate() -> None:
    case = _case("metric_engagement_complete_002")
    fixture = load_project_fixtures()[case.project_fixture]
    artifact = build_fixture_artifact(case, fixture).model_copy(
        update={
            "answer_text": (
                "Content 1 and Content 2 have confirmed views. "
                "Limitations: other public values are unavailable."
            )
        }
    )
    metrics = evaluate_with_ragas(
        case,
        artifact,
        build_reference_contexts(case, fixture),
    )

    checks = evaluate_rubric(case, artifact, fixture, metrics)

    assert (
        metrics["response_relevance_lexical"]
        < case.rubric.minimum_response_relevance
    )
    assert checks["response_relevance_quality"].passed is False


def test_missing_required_retrieval_source_fails_context_gate() -> None:
    case = _case("comparison_hooks_complete_008")
    fixture = load_project_fixtures()[case.project_fixture]
    artifact = build_fixture_artifact(case, fixture)
    metric_case = _case("metric_views_complete_001")
    metadata_evidence = build_fixture_artifact(metric_case, fixture).evidence
    metadata_only = artifact.model_copy(
        update={"evidence": metadata_evidence}
    )

    metrics = evaluate_with_ragas(
        case,
        metadata_only,
        build_reference_contexts(case, fixture),
    )
    checks = evaluate_rubric(case, metadata_only, fixture, metrics)

    assert metrics["context_relevance_lexical"] == 0.0
    assert checks["context_relevance_quality"].passed is False


def test_reference_contexts_are_not_read_from_candidate_artifact() -> None:
    case = _case("comparison_hooks_complete_008")
    fixture = load_project_fixtures()[case.project_fixture]
    artifact = build_fixture_artifact(case, fixture)
    artifact.evidence[0].text = "candidate-only-corruption-marker"

    reference_contexts = build_reference_contexts(case, fixture)

    assert reference_contexts
    assert all(
        "candidate-only-corruption-marker" not in text
        for text in reference_contexts
    )


def test_low_faithfulness_score_fails_case_gate() -> None:
    case = _case("metric_views_complete_001")
    fixture = load_project_fixtures()[case.project_fixture]
    artifact = build_fixture_artifact(case, fixture)
    metrics = {
        "faithfulness_lexical": 0.0,
        "response_relevance_lexical": 1.0,
        "context_relevance_lexical": 1.0,
    }

    checks = evaluate_rubric(case, artifact, fixture, metrics)

    assert checks["faithfulness_quality"].passed is False


def test_description_only_recommendation_is_grounded_and_passes() -> None:
    case = _case("recommendation_evidence_only_019")
    fixture = load_project_fixtures()[case.project_fixture]
    artifact = build_fixture_artifact(case, fixture)

    metrics = evaluate_with_ragas(
        case,
        artifact,
        build_reference_contexts(case, fixture),
    )
    checks = evaluate_rubric(case, artifact, fixture, metrics)

    assert "weekly creator planning template" in artifact.answer_text.casefold()
    assert metrics["faithfulness_lexical"] >= case.rubric.minimum_faithfulness
    assert all(check.passed for check in checks.values())
