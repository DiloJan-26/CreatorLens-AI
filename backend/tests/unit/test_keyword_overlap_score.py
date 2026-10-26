from app.rag.hybrid_search import keyword_overlap_score


def test_keyword_overlap_ignores_common_words_and_is_case_insensitive() -> None:
    score = keyword_overlap_score(
        "What makes the opening hook effective?",
        "The HOOK makes this opening clear and effective.",
    )

    assert score == 1.0


def test_keyword_overlap_is_zero_without_meaningful_overlap() -> None:
    assert keyword_overlap_score("opening hook", "monthly follower metrics") == 0.0
