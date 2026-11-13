from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings
from app.models.chat import LLMGenerationTestResponse, LLMHealthResponse


class LLMConfigurationError(Exception):
    """Raised when the configured LLM provider cannot be initialized."""


SUPPORTED_PROVIDER = "gemini"


def get_llm(
    streaming: bool = False,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    max_retries: int | None = None,
    timeout: float | None = None,
) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider != SUPPORTED_PROVIDER:
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}.")

    if not (settings.gemini_api_key or "").strip():
        raise LLMConfigurationError("GEMINI_API_KEY is missing.")

    return _get_gemini_llm(
        model=settings.llm_model,
        temperature=(
            settings.llm_temperature if temperature is None else temperature
        ),
        max_output_tokens=(
            settings.llm_max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        ),
        google_api_key=settings.gemini_api_key,
        streaming=streaming,
        max_retries=max_retries, timeout=timeout,
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


async def run_llm_generation_test(prompt: str) -> LLMGenerationTestResponse:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower() or SUPPORTED_PROVIDER
    safe_prompt = prompt.strip() or (
        "In one sentence, say that Gemini is connected for CreatorLens AI."
    )

    try:
        llm = get_llm(
            streaming=False,
            temperature=0.2,
            max_output_tokens=80, max_retries=0, timeout=30,
        )
        response = await _tracked_diagnostic_invoke(llm,safe_prompt,settings.llm_model)
        generated_text = _message_text(response).strip()

        if not generated_text:
            raise RuntimeError("Empty Gemini generation response.")

        return LLMGenerationTestResponse(
            status="ok",
            provider=provider,
            model=settings.llm_model,
            generated_text=generated_text,
            message=None,
        )
    except Exception:
        # Try configured fallback model if available — report which was used.
        fallback_model = (settings.llm_fallback_model or "").strip()
        if fallback_model and fallback_model != settings.llm_model:
            try:
                fallback_llm = _get_gemini_llm(
                    model=fallback_model,
                    temperature=0.2,
                    max_output_tokens=80,
                    google_api_key=settings.gemini_api_key or "",
                    streaming=False, max_retries=0, timeout=30,
                )
                response = await _tracked_diagnostic_invoke(fallback_llm,safe_prompt,fallback_model)
                generated_text = _message_text(response).strip()
                if generated_text:
                    return LLMGenerationTestResponse(
                        status="ok",
                        provider=provider,
                        model=fallback_model,
                        generated_text=generated_text,
                        message=(
                            f"Configured model ({settings.llm_model}) failed. "
                            f"Using fallback model: {fallback_model}. "
                            "Check AI Studio access or set LLM_MODEL to an available Gemini model."
                        ),
                    )
            except Exception:
                pass

        return LLMGenerationTestResponse(
            status="error",
            provider=provider,
            model=settings.llm_model,
            generated_text=None,
            message=(
                "Configured model failed. Check AI Studio access or set LLM_MODEL "
                "to an available Gemini model."
            ),
        )


@lru_cache
def _get_gemini_llm(
    model: str,
    temperature: float,
    max_output_tokens: int,
    google_api_key: str,
    streaming: bool,
    max_retries: int | None = None,
    timeout: float | None = None,
) -> ChatGoogleGenerativeAI:
    options = {} if max_retries is None else {"max_retries": max_retries}
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        google_api_key=google_api_key,
        streaming=streaming,
        timeout=timeout, **options,
    )


def _message_text(message: object) -> str:
    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])

        return "".join(parts)

    return ""


async def _tracked_diagnostic_invoke(llm, prompt, model):
    """Instrument the existing explicit diagnostic, without any fabricated project."""
    from time import perf_counter
    from app.llm.token_usage import TokenUsage,parse_token_usage
    from app.services.llm_observability_service import start_llm_run,complete_llm_run,fail_llm_run,record_cost_event,annotate_operation
    run=start_llm_run(project_id=None,llm_provider='gemini',llm_model=model,prompt_name='diagnostic_generation',prompt_version='1.0.0',
        operation_type='diagnostic_generation',execution_mode='runtime',provider_invocation_count=0)
    from app.llm.tracing import trace_span
    usage=TokenUsage();started=perf_counter();latency=None;span=None
    try:
        with trace_span('creatorlens.diagnostic_generation',run_type='llm',inputs={'message_count':1},
            metadata={'operation_type':'diagnostic_generation','operation_version':'1.0.0','execution_mode':'runtime','llm_model':model}) as span:
            invocation_started=perf_counter()
            try:
                response=await llm.ainvoke(prompt)
            finally:
                latency=round((perf_counter()-invocation_started)*1000)
        usage=parse_token_usage(response)
        if not _message_text(response).strip():raise ValueError('Empty diagnostic response.')
        complete_llm_run(run,usage=usage,llm_latency_ms=latency,provider_invocation_count=1,langsmith_trace_id=span.trace_id)
        return response
    except BaseException:
        latency=latency if latency is not None else round((perf_counter()-started)*1000)
        fail_llm_run(run,error_code='DIAGNOSTIC_GENERATION_FAILED',usage=usage,llm_latency_ms=latency,provider_invocation_count=1,langsmith_trace_id=getattr(span,'trace_id',None))
        raise
    finally:
        record_cost_event(llm_run_id=run,project_id=None,llm_provider='gemini',llm_model=model,usage=usage,provider_invocation_count=1)
        annotate_operation(run,usage=usage,end_to_end_latency_ms=round((perf_counter()-started)*1000),provider_invocation_count=1)
