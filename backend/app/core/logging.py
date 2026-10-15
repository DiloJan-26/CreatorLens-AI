import logging
import re
from collections.abc import Iterable

from app.core.config import Settings, get_settings


_SENSITIVE_QUERY_PARAMETER = re.compile(
    r"(?i)([?&](?:api[_-]?key|key|token|access[_-]?token|password|secret)=)"
    r"([^&\s\"']+)"
)
_CREDENTIAL_URL = re.compile(
    r"(?i)\b((?:https?|redis(?:s)?|postgres(?:ql)?(?:\+[a-z0-9]+)?)://)"
    r"([^/@\s]+)@"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic)\s+)([^\s,;]+)"
)
_API_KEY_HEADER_VALUE = re.compile(
    r"(?i)\b(x-goog-api-key\s*[:=]\s*)([^\s,;]+)"
)


def redact_sensitive_text(text: str, *, secret_values: Iterable[str] = ()) -> str:
    """Remove configured credentials and common credential URL shapes from logs."""
    redacted = text
    for secret in secret_values:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")

    redacted = _SENSITIVE_QUERY_PARAMETER.sub(r"\1[redacted]", redacted)
    redacted = _CREDENTIAL_URL.sub(r"\1[redacted]@", redacted)
    redacted = _AUTHORIZATION_VALUE.sub(r"\1[redacted]", redacted)
    return _API_KEY_HEADER_VALUE.sub(r"\1[redacted]", redacted)


class SecretRedactionFilter(logging.Filter):
    """Sanitize each formatted log message before a handler emits it."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        super().__init__()
        self._secret_values = tuple(value for value in secret_values if value)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(
            record.getMessage(),
            secret_values=self._secret_values,
        )
        record.args = ()
        return True


def configure_secret_safe_worker_logging(logger: logging.Logger) -> None:
    """Apply worker-specific log hardening after Celery creates its handlers."""
    secret_filter = SecretRedactionFilter(_configured_secret_values(get_settings()))
    for handler in logger.handlers:
        if not any(
            isinstance(existing_filter, SecretRedactionFilter)
            for existing_filter in handler.filters
        ):
            handler.addFilter(secret_filter)

    # HTTPX's INFO message contains the complete request URL. External request
    # outcomes remain available through application-level errors and retries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _configured_secret_values(settings: Settings) -> tuple[str, ...]:
    values = (
        settings.database_url,
        settings.test_database_url,
        settings.redis_url,
        settings.celery_broker_url_override,
        settings.celery_result_backend_override,
        settings.gemini_api_key,
        settings.groq_api_key,
        settings.qdrant_api_key,
        settings.youtube_api_key,
        settings.apify_api_token,
        settings.deepgram_api_key,
        settings.assemblyai_api_key,
    )
    return tuple(value for value in values if value)
