from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def available(self) -> bool:
        return any(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.total_tokens,
            )
        )


_INPUT_KEYS = (
    "input_tokens",
    "input_token_count",
    "prompt_tokens",
    "prompt_token_count",
)
_OUTPUT_KEYS = (
    "output_tokens",
    "output_token_count",
    "completion_tokens",
    "candidate_token_count",
    "candidates_token_count",
)
_TOTAL_KEYS = ("total_tokens", "total_token_count")


def parse_token_usage(response: object) -> TokenUsage:
    """Extract token counts without assuming one Gemini/LangChain shape.

    LangChain message metadata has changed across releases, so this parser
    accepts the documented usage_metadata shape as well as Gemini response
    metadata. Missing or malformed values remain unavailable.
    """

    sources = _usage_sources(response)
    input_tokens = _first_count(sources, _INPUT_KEYS)
    output_tokens = _first_count(sources, _OUTPUT_KEYS)
    total_tokens = _first_count(sources, _TOTAL_KEYS)

    if (
        total_tokens is None
        and input_tokens is not None
        and output_tokens is not None
    ):
        total_tokens = input_tokens + output_tokens

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _usage_sources(response: object) -> list[Mapping[str, Any]]:
    root = _as_mapping(response)
    sources: list[Mapping[str, Any]] = []

    direct_usage = _as_mapping(getattr(response, "usage_metadata", None))
    if direct_usage:
        sources.append(direct_usage)

    root_usage = _as_mapping(root.get("usage_metadata"))
    if root_usage:
        sources.append(root_usage)

    response_metadata = _as_mapping(
        getattr(response, "response_metadata", None)
    ) or _as_mapping(root.get("response_metadata"))
    _append_metadata_sources(sources, response_metadata)

    additional_kwargs = _as_mapping(
        getattr(response, "additional_kwargs", None)
    ) or _as_mapping(root.get("additional_kwargs"))
    _append_metadata_sources(sources, additional_kwargs)

    if root:
        sources.append(root)

    return sources


def _append_metadata_sources(
    sources: list[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> None:
    if not metadata:
        return
    for key in ("usage_metadata", "token_usage", "usage"):
        nested = _as_mapping(metadata.get(key))
        if nested:
            sources.append(nested)
    sources.append(metadata)


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    return {}


def _first_count(
    sources: list[Mapping[str, Any]],
    keys: tuple[str, ...],
) -> int | None:
    for source in sources:
        for key in keys:
            value = _nonnegative_int(source.get(key))
            if value is not None:
                return value
    return None


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
