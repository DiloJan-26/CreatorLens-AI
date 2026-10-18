import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.llm.citation_service import validate_evidence_items
from app.llm.structured_outputs import (
    ComparisonAnswer,
    MetricAnswer,
    MetricItem,
    RecommendationAnswer,
    StructuredAnswer,
    StructuredAnswerType,
    answer_has_factual_claims,
)
from app.models.chat import Citation


class StructuredOutputParseResult(BaseModel):
    answer: StructuredAnswer
    used_fallback: bool = False
    warnings: list[str] = Field(default_factory=list)


def parse_structured_output(
    raw_output: str,
    answer_type: StructuredAnswerType | str,
    *,
    citations: Sequence[Citation] | None = None,
) -> StructuredOutputParseResult:
    normalized_type = StructuredAnswerType(answer_type)

    try:
        payload = _extract_json_object(raw_output)
        payload.setdefault("answer_type", normalized_type.value)
        answer = _schema_for(normalized_type).model_validate(payload)
    except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
        warning = (
            "The model response could not be validated, so a safe "
            "insufficient-evidence response was returned."
        )
        return StructuredOutputParseResult(
            answer=_fallback_answer(normalized_type, warning),
            used_fallback=True,
            warnings=[warning],
        )

    if citations is None:
        return StructuredOutputParseResult(answer=answer)

    validation = validate_evidence_items(
        answer.evidence,
        citations,
        factual_claims_present=answer_has_factual_claims(answer),
    )
    answer = _apply_citation_validation(
        answer,
        grounded_evidence=validation.evidence,
        valid_citation_labels={item.citation_label for item in validation.evidence},
        warnings=validation.warnings,
    )
    return StructuredOutputParseResult(
        answer=answer,
        used_fallback=False,
        warnings=validation.warnings,
    )


def _extract_json_object(raw_output: str) -> dict[str, Any]:
    value = raw_output.strip()
    if not value:
        raise ValueError("Model output is empty.")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1)

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])

    if not isinstance(parsed, dict):
        raise TypeError("Structured output must be a JSON object.")
    return parsed


def _schema_for(answer_type: StructuredAnswerType) -> type[BaseModel]:
    return {
        StructuredAnswerType.METRIC: MetricAnswer,
        StructuredAnswerType.COMPARISON: ComparisonAnswer,
        StructuredAnswerType.RECOMMENDATION: RecommendationAnswer,
    }[answer_type]


def _fallback_answer(
    answer_type: StructuredAnswerType,
    warning: str,
) -> StructuredAnswer:
    if answer_type == StructuredAnswerType.METRIC:
        return MetricAnswer(
            summary="Confirmed metric evidence is unavailable.",
            limitations=[warning],
        )
    if answer_type == StructuredAnswerType.COMPARISON:
        return ComparisonAnswer(
            winner="insufficient_evidence",
            confidence=0.0,
            limitations=[warning],
        )
    return RecommendationAnswer(
        summary="Evidence-backed recommendations are unavailable.",
        limitations=[warning],
    )


def _apply_citation_validation(
    answer: StructuredAnswer,
    *,
    grounded_evidence: list,
    valid_citation_labels: set[str],
    warnings: list[str],
) -> StructuredAnswer:
    limitations = list(dict.fromkeys([*answer.limitations, *warnings]))

    if isinstance(answer, MetricAnswer):
        metrics = [
            metric
            if metric.availability == "unavailable"
            or metric.citation_label in valid_citation_labels
            else MetricItem(
                name=metric.name,
                slot=metric.slot,
                availability="unavailable",
            )
            for metric in answer.metrics
        ]
        return answer.model_copy(
            update={
                "metrics": metrics,
                "evidence": grounded_evidence,
                "limitations": limitations,
            }
        )

    if isinstance(answer, ComparisonAnswer) and answer_has_factual_claims(answer) and not grounded_evidence:
        return answer.model_copy(
            update={
                "winner": "insufficient_evidence",
                "confidence": 0.0,
                "key_reasons": [],
                "evidence": [],
                "limitations": limitations,
            }
        )

    return answer.model_copy(
        update={
            "evidence": grounded_evidence,
            "limitations": limitations,
        }
    )

