import pytest
from pydantic import ValidationError

from app.llm.structured_outputs import MetricAnswer, MetricItem


def test_confirmed_metric_requires_value_and_citation() -> None:
    answer = MetricAnswer(
        summary="Content 1 has more confirmed views.",
        metrics=[
            MetricItem(
                name="views",
                slot="content_1",
                value=1200,
                availability="confirmed",
                citation_label="Content 1 metadata",
            )
        ],
    )

    assert answer.metrics[0].value == 1200

    with pytest.raises(ValidationError):
        MetricItem(
            name="views",
            slot="content_1",
            value=1200,
            availability="confirmed",
        )


def test_unavailable_metric_cannot_contain_an_estimate() -> None:
    with pytest.raises(ValidationError):
        MetricItem(
            name="views",
            slot="content_2",
            value=500,
            availability="unavailable",
        )

