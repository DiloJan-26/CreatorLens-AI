import json

from app.llm.citation_service import MISSING_EVIDENCE_WARNING
from app.llm.structured_output_service import parse_structured_output


def test_comparison_without_available_citations_is_downgraded() -> None:
    result = parse_structured_output(
        json.dumps(
            {
                "answer_type": "comparison",
                "winner": "content_1",
                "confidence": 0.9,
                "key_reasons": ["Content 1 has a stronger hook."],
                "evidence": [],
                "limitations": [],
                "recommendations": [],
            }
        ),
        "comparison",
        citations=[],
    )

    assert result.answer.winner == "insufficient_evidence"
    assert result.answer.confidence == 0.0
    assert MISSING_EVIDENCE_WARNING in result.answer.limitations

