import json

from app.llm.structured_output_service import parse_structured_output
from app.models.chat import Citation


def test_unrecognized_metric_citation_is_not_treated_as_confirmed() -> None:
    result = parse_structured_output(
        json.dumps(
            {
                "answer_type": "metric",
                "summary": "Content 1 has 1000 views.",
                "metrics": [
                    {
                        "name": "views",
                        "slot": "content_1",
                        "value": 1000,
                        "availability": "confirmed",
                        "citation_label": "Invented citation",
                    }
                ],
                "evidence": [
                    {
                        "citation_label": "Invented citation",
                        "claim": "Content 1 has 1000 views.",
                    }
                ],
                "limitations": [],
            }
        ),
        "metric",
        citations=[
            Citation(
                slot="content_1",
                platform="YouTube",
                source_type="metadata",
                citation_label="Content 1 metadata",
                text="Views: Unavailable",
            )
        ],
    )

    assert result.answer.metrics[0].availability == "unavailable"
    assert result.answer.metrics[0].value is None
    assert result.answer.evidence == []
    assert result.answer.limitations

