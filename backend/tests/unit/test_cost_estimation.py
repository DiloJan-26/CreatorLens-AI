from decimal import Decimal

from app.llm.cost_estimation import estimate_cost_usd
from app.llm.token_usage import TokenUsage


def test_cost_estimation_uses_configured_per_million_rates() -> None:
    result = estimate_cost_usd(
        TokenUsage(input_tokens=1_000_000, output_tokens=500_000),
        input_cost_per_million_usd=0.10,
        output_cost_per_million_usd=0.40,
    )

    assert result == Decimal("0.30000000")


def test_cost_estimation_stays_unavailable_without_rates() -> None:
    result = estimate_cost_usd(
        TokenUsage(input_tokens=100, output_tokens=20),
        input_cost_per_million_usd=None,
        output_cost_per_million_usd=None,
    )

    assert result is None
