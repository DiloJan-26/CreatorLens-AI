import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.llm.citation_service import validate_evidence_items
from app.llm.structured_outputs import (
    ComparisonAnswer,
    EvidenceItem,
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
    canonical_context: dict | None = None,
    question: str = "",
    intent: str = "general",
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
        if canonical_context is not None:
            from app.rag.intelligence_context import canonical_answer
            return StructuredOutputParseResult(answer=canonical_answer(canonical_context,question,intent,list(citations or [])),used_fallback=True,warnings=["Generated JSON was invalid; the current canonical answer was retained."])
        return StructuredOutputParseResult(
            answer=_fallback_answer(normalized_type, warning),
            used_fallback=True,
            warnings=[warning],
        )

    if canonical_context is not None:
        from app.llm.assistant_grounding import validate_generated_answer
        answer,warnings=validate_generated_answer(answer,canonical_context,question,intent,list(citations or []))
        return StructuredOutputParseResult(answer=answer,used_fallback=bool(warnings),warnings=warnings)
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


def structured_answer_json_schema(
    answer_type: StructuredAnswerType | str,
) -> dict[str, Any]:
    return _schema_for(StructuredAnswerType(answer_type)).model_json_schema()


def render_structured_answer(answer: StructuredAnswer) -> str:
    if isinstance(answer, MetricAnswer):
        lines = [answer.summary]
        if answer.metrics:
            lines.extend(["", "## Confirmed metrics"])
            for metric in answer.metrics:
                slot = _slot_label(metric.slot)
                value = metric.value if metric.availability == "confirmed" else "Unavailable"
                lines.append(f"- **{slot} {metric.name}:** {value}")
    elif isinstance(answer, ComparisonAnswer):
        lines = [
            f"## Verdict\n{_winner_label(answer.winner)}",
            f"**Objective:** {answer.objective or 'not specified'}; **Evidence status:** {answer.evidence_status}",
        ]
        if answer.key_reasons:
            lines.extend(["", "## Key reasons"])
            lines.extend(
                f"{index}. {reason}"
                for index, reason in enumerate(answer.key_reasons, start=1)
            )
        if answer.recommendations:
            lines.extend(["", "## Recommendations"])
            lines.extend(_recommendation_lines(answer.recommendations))
    else:
        lines = [answer.summary]
        if answer.recommendations:
            lines.extend(["", "## Recommendations"])
            lines.extend(_recommendation_lines(answer.recommendations))

    if isinstance(answer, RecommendationAnswer) and answer.hypothetical_draft:
        lines.extend(["", "## Hypothetical draft (not a measured improvement)", answer.hypothetical_draft.text])
    if answer.limitations:
        lines.extend(["", "## Limitations"])
        lines.extend(f"- {limitation}" for limitation in answer.limitations)

    return "\n".join(lines).strip()



def _recommendation_lines(items) -> list[str]:
    lines=[]
    for index,item in enumerate(items,start=1):
        target=(_slot_label(item.target_slot)+": ") if item.target_slot else ""
        lines.append(f"{index}. **{target}{item.recommendation}** ({item.priority} priority) - {item.rationale}")
        if item.experiment:lines.append("   - Experiment: "+item.experiment)
        if item.limitation:lines.append("   - Limitation: "+item.limitation)
    return lines


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
    grounded_evidence: list[EvidenceItem],
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

    recommendations = [
        item.model_copy(
            update={
                "citation_labels": [
                    label
                    for label in item.citation_labels
                    if label in valid_citation_labels
                ]
            }
        )
        for item in answer.recommendations
    ]

    return answer.model_copy(
        update={
            "evidence": grounded_evidence,
            "limitations": limitations,
            "recommendations": recommendations,
        }
    )


def _slot_label(slot: str) -> str:
    return "Content 1" if slot == "content_1" else "Content 2"


def _winner_label(winner: str) -> str:
    return {
        "content_1": "Content 1 has the stronger supported result.",
        "content_2": "Content 2 has the stronger supported result.",
        "tie": "The available evidence supports a tie.",
        "insufficient_evidence": "There is insufficient evidence to name a winner.",
    }[winner]

