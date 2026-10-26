from app.evaluations.rubric_checks import check_forbidden_claims


def test_forbidden_claim_check_is_case_insensitive() -> None:
    result = check_forbidden_claims(
        "This result guarantees VIRALITY next week.",
        ["guarantees virality"],
    )

    assert result.passed is False


def test_forbidden_claim_check_accepts_grounded_text() -> None:
    result = check_forbidden_claims(
        "The confirmed evidence supports a cautious recommendation.",
        ["guaranteed virality"],
    )

    assert result.passed is True
