"""Resource-light RAGAS evaluation boundary.

The runner validates samples with RAGAS and calculates deterministic lexical
metrics without invoking a paid model judge. The metric names deliberately
identify their lexical nature so they are not confused with LLM-judge scores.
"""

from __future__ import annotations

import re
from importlib import import_module

from app.evaluations.ragas_compat import load_ragas
from app.schemas.evaluation import EvaluationArtifact, EvaluationCaseDefinition


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "based", "by", "for",
    "from", "has", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "using", "was", "were", "which", "with",
}


def evaluate_with_ragas(
    case: EvaluationCaseDefinition,
    artifact: EvaluationArtifact,
) -> dict[str, float]:
    ragas = load_ragas()
    reference_contexts = [
        item.text
        for item in artifact.evidence
        if item.source_type in set(case.required_sources)
    ] or artifact.retrieved_contexts
    sample = ragas.SingleTurnSample(
        user_input=case.question,
        response=artifact.answer_text,
        retrieved_contexts=artifact.retrieved_contexts,
        reference_contexts=reference_contexts,
    )
    sample.model_dump()  # Validate the installed RAGAS data contract.

    # RAGAS 0.4.3 emits a deprecated-import warning for these non-LLM metrics,
    # while its advertised collections module does not export them yet. Import
    # their pinned 0.4 implementation modules directly until that gap is fixed.
    context_recall_module = import_module("ragas.metrics._context_recall")
    context_precision_module = import_module("ragas.metrics._context_precision")
    context_recall = (
        context_recall_module.NonLLMContextRecall().single_turn_score(sample)
    )
    context_precision = (
        context_precision_module.NonLLMContextPrecisionWithReference()
        .single_turn_score(sample)
    )

    question_tokens = _tokens(case.question)
    answer_tokens = _tokens(artifact.answer_text)
    context_tokens = _tokens(" ".join(artifact.retrieved_contexts))

    faithfulness = _coverage(answer_tokens, context_tokens)
    response_relevance = _symmetric_overlap(question_tokens, answer_tokens)
    context_relevance = _coverage(question_tokens, context_tokens)
    return {
        "faithfulness_lexical": faithfulness,
        "response_relevance_lexical": response_relevance,
        "context_relevance_lexical": context_relevance,
        "context_recall_ragas": round(float(context_recall), 6),
        "context_precision_ragas": round(float(context_precision), 6),
    }


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _coverage(expected: set[str], observed: set[str]) -> float:
    if not expected:
        return 1.0
    return round(len(expected & observed) / len(expected), 6)


def _symmetric_overlap(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return round(len(left & right) / len(union), 6) if union else 0.0
