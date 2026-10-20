from decimal import Decimal

from app.llm.token_usage import TokenUsage


MILLION = Decimal("1000000")


def estimate_cost_usd(
    usage: TokenUsage,
    *,
    input_cost_per_million_usd: float | None,
    output_cost_per_million_usd: float | None,
) -> Decimal | None:
    """Estimate model cost only when both usage and configured rates exist."""

    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    if (
        input_cost_per_million_usd is None
        or output_cost_per_million_usd is None
    ):
        return None

    input_cost = (
        Decimal(usage.input_tokens)
        * Decimal(str(input_cost_per_million_usd))
        / MILLION
    )
    output_cost = (
        Decimal(usage.output_tokens)
        * Decimal(str(output_cost_per_million_usd))
        / MILLION
    )
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))
