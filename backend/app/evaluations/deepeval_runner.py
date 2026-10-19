"""DeepEval test-case adapter with deterministic CreatorLens rubrics."""

from __future__ import annotations

import os

from app.evaluations.rubric_checks import evaluate_rubric
from app.schemas.evaluation import (
    EvaluationArtifact,
    EvaluationCaseDefinition,
    EvaluationCheckResult,
    EvaluationProjectFixture,
)


def evaluate_with_deepeval(
    case: EvaluationCaseDefinition,
    artifact: EvaluationArtifact,
    fixture: EvaluationProjectFixture,
    metric_scores: dict[str, float],
) -> dict[str, EvaluationCheckResult]:
    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "true")
    from deepeval.test_case import LLMTestCase

    test_case = LLMTestCase(
        input=case.question,
        actual_output=artifact.answer_text,
        retrieval_context=artifact.retrieved_contexts,
    )
    if test_case.input != case.question or test_case.actual_output != artifact.answer_text:
        raise ValueError("DeepEval test-case construction changed evaluation content.")
    return evaluate_rubric(case, artifact, fixture, metric_scores)
