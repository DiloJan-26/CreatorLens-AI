from app.llm.structured_outputs import ComparisonAnswer, EvidenceItem


def test_comparison_answer_accepts_grounded_evidence() -> None:
    answer = ComparisonAnswer(
        winner="content_1",
        confidence=0.8,
        key_reasons=["Content 1 has the stronger opening."],
        evidence=[
            EvidenceItem(
                citation_label="Content 1 hook",
                claim="The opening states the result immediately.",
            )
        ],
        limitations=["Content 2 view count is unavailable."],
    )

    assert answer.answer_type == "comparison"
    assert answer.winner == "content_1"

