"""Shared API/worker model policy, without implicit model substitution."""
from typing import Any

SUPPORTED_GEMINI_MODELS = frozenset({
    'gemini-3.5-flash-lite',
    'gemini-3.6-flash',
    'gemini-3.8-flash',
})
DEFAULT_GEMINI_MODEL = 'gemini-3.5-flash-lite'


def model_configuration_error(settings: Any) -> str | None:
    if settings.llm_provider != 'gemini':
        return 'Only the Gemini Developer API provider is supported.'
    if settings.llm_model not in SUPPORTED_GEMINI_MODELS:
        return 'LLM_MODEL must be an exact approved Gemini model ID.'
    environment = getattr(settings, 'environment', 'local').strip().lower()
    fields = getattr(settings, 'model_fields_set', set())
    if environment not in {'local', 'test'} and 'llm_model' not in fields:
        return 'LLM_MODEL must be explicitly configured for the deployed API and worker.'
    fallback = getattr(settings, 'llm_fallback_model', None)
    if fallback and fallback != settings.llm_model:
        return 'Automatic model fallback is disabled; configure only LLM_MODEL.'
    return None


def require_supported_model(model: str) -> None:
    if model not in SUPPORTED_GEMINI_MODELS:
        raise ValueError('An exact approved Gemini model ID is required.')
