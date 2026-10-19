"""Deterministic safety and grounding checks for evaluation artifacts."""

from __future__ import annotations

import re

from app.schemas.evaluation import (
    EvaluationArtifact,
    EvaluationCaseDefinition,
    EvaluationCheckResult,
    EvaluationProjectFixture,
)


def check_citation_presence(artifact: EvaluationArtifact) -> EvaluationCheckResult:
    passed = bool(artifact.citation_labels)
    return EvaluationCheckResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        message="Evidence citations are present." if passed else "No evidence citations were supplied.",
    )


def check_forbidden_claims(
    answer_text: str,
    forbidden_claims: list[str],
) -> EvaluationCheckResult:
    normalized = answer_text.casefold()
    matches = [claim for claim in forbidden_claims if claim.casefold() in normalized]
    passed = not matches
    return EvaluationCheckResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        message=(
            "No forbidden claims were found."
            if passed
            else f"Forbidden claims found: {', '.join(matches)}."
        ),
    )


def check_missing_metric_compliance(
    artifact: EvaluationArtifact,
    fixture: EvaluationProjectFixture,
) -> EvaluationCheckResult:
    violations: list[str] = []
    text = artifact.answer_text.casefold()
    for content in fixture.contents:
        slot_label = "content 1" if content.slot == "content_1" else "content 2"
        for metric, value in content.metadata.items():
            if metric == "missing_fields" or value is not None:
                continue
            readable_metric = metric.replace("_", " ")
            patterns = (
                rf"{re.escape(slot_label)}[^.\n]{{0,80}}{re.escape(readable_metric)}\s*(?:is|was|:|=)\s*\d",
                rf"{re.escape(readable_metric)}[^.\n]{{0,40}}{re.escape(slot_label)}\s*(?:is|was|:|=)\s*\d",
            )
            if any(re.search(pattern, text) for pattern in patterns):
                violations.append(f"{slot_label} {readable_metric}")

    passed = not violations
    return EvaluationCheckResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        message=(
            "Unavailable metrics were not converted into confirmed values."
            if passed
            else f"Unavailable metrics received numeric values: {', '.join(violations)}."
        ),
    )


def check_required_sources(
    artifact: EvaluationArtifact,
    required_sources: list[str],
) -> EvaluationCheckResult:
    present = {item.source_type for item in artifact.evidence}
    missing = sorted(set(required_sources) - present)
    passed = not missing
    return EvaluationCheckResult(
        passed=passed,
        score=(len(set(required_sources) & present) / len(set(required_sources)))
        if required_sources
        else 1.0,
        message=(
            "All required evidence source types are present."
            if passed
            else f"Missing evidence source types: {', '.join(missing)}."
        ),
    )


def check_both_content_comparison(artifact: EvaluationArtifact) -> EvaluationCheckResult:
    slots = {item.slot for item in artifact.evidence}
    mentioned = "content 1" in artifact.answer_text.casefold() and "content 2" in artifact.answer_text.casefold()
    passed = slots == {"content_1", "content_2"} and mentioned
    return EvaluationCheckResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        message=(
            "Both content slots are represented in the answer and evidence."
            if passed
            else "The comparison does not represent both content slots."
        ),
    )


def evaluate_rubric(
    case: EvaluationCaseDefinition,
    artifact: EvaluationArtifact,
    fixture: EvaluationProjectFixture,
    metric_scores: dict[str, float] | None = None,
) -> dict[str, EvaluationCheckResult]:
    answer_type_passed = artifact.answer_type == case.expected_answer_type
    checks = {
        "answer_type": EvaluationCheckResult(
            passed=answer_type_passed,
            score=1.0 if answer_type_passed else 0.0,
            message=(
                "Answer type matches the dataset contract."
                if answer_type_passed
                else "Answer type does not match the dataset contract."
            ),
        ),
        "required_sources": check_required_sources(artifact, case.required_sources),
        "forbidden_claims": check_forbidden_claims(artifact.answer_text, case.forbidden_claims),
    }
    if case.rubric.must_cite_evidence:
        checks["citation_presence"] = check_citation_presence(artifact)
    if case.rubric.must_not_estimate_missing_metrics:
        checks["missing_metric_compliance"] = check_missing_metric_compliance(artifact, fixture)
    if case.rubric.must_compare_both_contents:
        checks["both_content_comparison"] = check_both_content_comparison(artifact)
    if case.rubric.must_report_limitations:
        passed = bool(artifact.limitations)
        checks["limitations_present"] = EvaluationCheckResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            message="Limitations are explicit." if passed else "Limitations are missing.",
        )
    if metric_scores is not None:
        thresholds = {
            "faithfulness_quality": (
                "faithfulness_lexical",
                case.rubric.minimum_faithfulness,
            ),
            "response_relevance_quality": (
                "response_relevance_lexical",
                case.rubric.minimum_response_relevance,
            ),
            "context_relevance_quality": (
                "context_relevance_lexical",
                case.rubric.minimum_context_relevance,
            ),
        }
        for check_name, (metric_name, minimum) in thresholds.items():
            score = metric_scores.get(metric_name, 0.0)
            passed = score >= minimum
            checks[check_name] = EvaluationCheckResult(
                passed=passed,
                score=score,
                message=(
                    f"{metric_name} meets the {minimum:.2f} minimum."
                    if passed
                    else f"{metric_name} is below the {minimum:.2f} minimum."
                ),
            )
    return checks
