from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings
from app.models.chat import LLMHealthResponse


class LLMConfigurationError(Exception):
    """Raised when the configured LLM provider cannot be initialized."""


SUPPORTED_PROVIDER = "gemini"


def get_llm(streaming: bool = False) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider != SUPPORTED_PROVIDER:
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}.")

    if not (settings.gemini_api_key or "").strip():
        raise LLMConfigurationError("GEMINI_API_KEY is missing.")

    return _get_gemini_llm(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        google_api_key=settings.gemini_api_key,
        streaming=streaming,
    )


def check_llm_configured() -> LLMHealthResponse:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower() or SUPPORTED_PROVIDER

    if provider != SUPPORTED_PROVIDER:
        return LLMHealthResponse(
            status="error",
            provider=settings.llm_provider,
            model=settings.llm_model,
            configured=False,
            message="Unsupported LLM provider.",
        )

    if not (settings.gemini_api_key or "").strip():
        return LLMHealthResponse(
            status="not_configured",
            provider=provider,
            model=settings.llm_model,
            configured=False,
            message="GEMINI_API_KEY is missing.",
        )

    try:
        get_llm(streaming=False)
    except LLMConfigurationError as exc:
        return LLMHealthResponse(
            status="not_configured",
            provider=provider,
            model=settings.llm_model,
            configured=False,
            message=str(exc),
        )
    except Exception:
        return LLMHealthResponse(
            status="error",
            provider=provider,
            model=settings.llm_model,
            configured=False,
            message="Could not initialize LLM client.",
        )

    return LLMHealthResponse(
        status="ok",
        provider=provider,
        model=settings.llm_model,
        configured=True,
    )


@lru_cache
def _get_gemini_llm(
    model: str,
    temperature: float,
    max_output_tokens: int,
    google_api_key: str,
    streaming: bool,
) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        google_api_key=google_api_key,
        streaming=streaming,
    )
