from types import SimpleNamespace

from app.llm.token_usage import TokenUsage, parse_token_usage


def test_token_usage_parser_reads_langchain_usage_metadata() -> None:
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
        }
    )

    assert parse_token_usage(response) == TokenUsage(120, 30, 150)


def test_token_usage_parser_reads_gemini_response_metadata() -> None:
    response = SimpleNamespace(
        usage_metadata=None,
        response_metadata={
            "usage_metadata": {
                "prompt_token_count": "90",
                "candidates_token_count": 15,
                "total_token_count": 105,
            }
        },
    )

    assert parse_token_usage(response) == TokenUsage(90, 15, 105)


def test_token_usage_parser_handles_missing_or_invalid_values() -> None:
    response = {
        "usage_metadata": {
            "input_tokens": -1,
            "output_tokens": True,
            "total_tokens": "unknown",
        }
    }

    usage = parse_token_usage(response)

    assert usage == TokenUsage()
    assert usage.available is False


def test_token_usage_parser_derives_total_from_available_parts() -> None:
    response = {"usage_metadata": {"prompt_tokens": 10, "completion_tokens": 4}}

    assert parse_token_usage(response) == TokenUsage(10, 4, 14)
