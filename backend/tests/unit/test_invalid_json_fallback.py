from app.llm.structured_output_service import parse_structured_output
from app.llm.structured_outputs import ComparisonAnswer


def test_invalid_json_returns_safe_comparison_fallback() -> None:
    result = parse_structured_output(
        "This is not valid JSON.",
        "comparison",
    )

    assert result.used_fallback is True
    assert isinstance(result.answer, ComparisonAnswer)
    assert result.answer.winner == "insufficient_evidence"
    assert result.answer.confidence == 0.0
    assert result.answer.limitations


def test_json_code_fence_is_parsed() -> None:
    result = parse_structured_output(
        """```json
        {
          "answer_type": "comparison",
          "winner": "tie",
          "confidence": 0.5,
          "key_reasons": [],
          "evidence": [],
          "limitations": ["Metrics are incomplete."],
          "recommendations": []
        }
        ```""",
        "comparison",
    )

    assert result.used_fallback is False
    assert result.answer.winner == "tie"

