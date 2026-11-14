from typing import Literal
from functools import lru_cache
from app.core.model_policy import DEFAULT_GEMINI_MODEL

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    demo_access_mode: Literal["disabled", "local"] = Field(default="disabled", alias="DEMO_ACCESS_MODE")
    demo_allow_provider_calls: bool = Field(default=False, alias="DEMO_ALLOW_PROVIDER_CALLS")
    application_access_mode: Literal["disabled", "authenticated"] = Field(default="disabled", alias="APPLICATION_ACCESS_MODE")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_jwt_issuer: str | None = Field(default=None, alias="SUPABASE_JWT_ISSUER")
    supabase_jwks_url: str | None = Field(default=None, alias="SUPABASE_JWKS_URL")
    supabase_jwt_audience: str = Field(default="authenticated", alias="SUPABASE_JWT_AUDIENCE")
    authenticated_requests_per_minute: int = Field(default=0, alias="AUTHENTICATED_REQUESTS_PER_MINUTE", ge=0)
    analysis_requests_per_minute: int = Field(default=0, alias="ANALYSIS_REQUESTS_PER_MINUTE", ge=0)
    paid_requests_per_minute: int = Field(default=0, alias="PAID_REQUESTS_PER_MINUTE", ge=0)
    provider_input_byte_limit: int = Field(default=0, alias="PROVIDER_INPUT_BYTE_LIMIT", ge=0, le=131072)
    paid_operations_enabled: bool = Field(default=False, alias="PAID_OPERATIONS_ENABLED")
    user_budget_usd: str = Field(default="0", alias="USER_BUDGET_USD")
    global_budget_usd: str = Field(default="0", alias="GLOBAL_BUDGET_USD")
    provider_operation_ceiling_usd: str = Field(default="0", alias="PROVIDER_OPERATION_CEILING_USD")

    extraction_enabled: bool = Field(default=False, alias="EXTRACTION_ENABLED")
    extraction_max_concurrent_operations: int = Field(default=0, alias="EXTRACTION_MAX_CONCURRENT_OPERATIONS", ge=0, le=16)
    extraction_max_video_seconds: int = Field(default=0, alias="EXTRACTION_MAX_VIDEO_SECONDS", ge=0, le=86400)
    extraction_max_url_bytes: int = Field(default=0, alias="EXTRACTION_MAX_URL_BYTES", ge=0, le=8192)
    extraction_max_response_bytes: int = Field(default=0, alias="EXTRACTION_MAX_RESPONSE_BYTES", ge=0, le=16777216)
    extraction_timeout_seconds: int = Field(default=0, alias="EXTRACTION_TIMEOUT_SECONDS", ge=0, le=120)
    supadata_billing_tier: str = Field(default="", alias="SUPADATA_BILLING_TIER")
    supadata_prepaid_verified: bool = Field(default=False, alias="SUPADATA_PREPAID_VERIFIED")
    supadata_auto_recharge_disabled: bool = Field(default=False, alias="SUPADATA_AUTO_RECHARGE_DISABLED")
    supadata_credit_pool: str = Field(default="", alias="SUPADATA_CREDIT_POOL")
    supadata_credit_limit: int = Field(default=0, alias="SUPADATA_CREDIT_LIMIT", ge=0, le=3000)

    @model_validator(mode="after")
    def validate_authenticated_configuration(self):
        if self.application_access_mode != "authenticated":
            return self
        from urllib.parse import urlsplit
        from decimal import Decimal
        base = (self.supabase_url or "").rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.username:
            raise ValueError("Authenticated mode requires a trusted HTTPS Supabase origin.")
        if self.supabase_jwt_issuer != base + "/auth/v1" or self.supabase_jwks_url != base + "/auth/v1/.well-known/jwks.json":
            raise ValueError("Supabase issuer and JWKS must match the configured origin.")
        if self.supabase_jwt_audience != "authenticated" or not self.database_url or not self.redis_url:
            raise ValueError("Authenticated mode requires the authenticated audience, PostgreSQL and Redis.")
        if not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise ValueError("Authenticated mode requires PostgreSQL persistence.")
        if self.demo_access_mode != "disabled":
            raise ValueError("Authenticated access cannot enable the legacy local demo bypass.")
        for value in (self.user_budget_usd, self.global_budget_usd, self.provider_operation_ceiling_usd):
            number = Decimal(value)
            if not number.is_finite() or number < 0:
                raise ValueError("Budget values must be finite and nonnegative.")
        if self.paid_operations_enabled and (not self.paid_requests_per_minute or any(Decimal(v) <= 0 for v in (self.user_budget_usd, self.global_budget_usd, self.provider_operation_ceiling_usd))):
            raise ValueError("Paid operations require explicit nonzero rate and budget bounds.")
        if not self.authenticated_requests_per_minute:
            raise ValueError("Authenticated mode requires an explicitly configured request rate.")
        if self.extraction_enabled:
            from app.extraction.policy import configuration
            try:
                configuration(self)
            except Exception:
                raise ValueError("Extraction requires approved provider-specific account, pricing and execution bounds.") from None
        return self

    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    test_database_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE", ge=1, le=20)
    db_max_overflow: int = Field(default=5, alias="DB_MAX_OVERFLOW", ge=0, le=20)
    db_pool_recycle_seconds: int = Field(
        default=300,
        alias="DB_POOL_RECYCLE_SECONDS",
        ge=30,
    )
    db_connect_timeout_seconds: int = Field(
        default=10,
        alias="DB_CONNECT_TIMEOUT_SECONDS",
        ge=1,
        le=60,
    )

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    celery_broker_url_override: str | None = Field(
        default=None,
        alias="CELERY_BROKER_URL",
    )
    celery_result_backend_override: str | None = Field(
        default=None,
        alias="CELERY_RESULT_BACKEND",
    )
    celery_result_expires_seconds: int = Field(
        default=3600,
        alias="CELERY_RESULT_EXPIRES_SECONDS",
        ge=60,
        le=86400,
    )
    celery_visibility_timeout_seconds: int = Field(
        default=3600,
        alias="CELERY_VISIBILITY_TIMEOUT_SECONDS",
        ge=300,
        le=86400,
    )
    celery_max_retries: int = Field(
        default=2,
        alias="CELERY_MAX_RETRIES",
        ge=0,
        le=5,
    )
    celery_retry_backoff_seconds: int = Field(
        default=15,
        alias="CELERY_RETRY_BACKOFF_SECONDS",
        ge=1,
        le=300,
    )
    celery_broker_connection_timeout_seconds: int = Field(
        default=5,
        alias="CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS",
        ge=1,
        le=30,
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    semantic_supported_languages: str = Field(default="en,hi,ta", alias="SEMANTIC_SUPPORTED_LANGUAGES")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default=DEFAULT_GEMINI_MODEL, alias="LLM_MODEL")
    llm_fallback_model: str | None = Field(default=None, alias="LLM_FALLBACK_MODEL")
    llm_temperature: float = Field(default=0.35, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(
        default=2200,
        alias="LLM_MAX_OUTPUT_TOKENS", ge=1, le=8192,
    )
    llm_input_cost_per_million_usd: float | None = Field(
        default=None,
        alias="LLM_INPUT_COST_PER_MILLION_USD",
        ge=0,
    )
    llm_output_cost_per_million_usd: float | None = Field(
        default=None,
        alias="LLM_OUTPUT_COST_PER_MILLION_USD",
        ge=0,
    )
    llm_estimate_service_tier: str | None = Field(default=None, alias="LLM_ESTIMATE_SERVICE_TIER")
    llm_cache_billing_mode: str = Field(default="unknown", alias="LLM_CACHE_BILLING_MODE")
    debug_rag_prompt: bool = Field(default=False, alias="DEBUG_RAG_PROMPT")

    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="creatorlens-local",
        alias="LANGSMITH_PROJECT",
    )
    langsmith_endpoint: str | None = Field(
        default=None,
        alias="LANGSMITH_ENDPOINT",
    )
    langsmith_workspace_id: str | None = Field(
        default=None,
        alias="LANGSMITH_WORKSPACE_ID",
    )

    qdrant_url: str | None = Field(default=None, alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="creatorlens_chunks",
        alias="QDRANT_COLLECTION",
    )
    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5",
        alias="EMBEDDING_MODEL_NAME",
    )
    embedding_model_version: str = Field(
        default="1",
        alias="EMBEDDING_MODEL_VERSION",
    )

    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    supadata_api_key: str | None = Field(default=None, alias="SUPADATA_API_KEY")
    supadata_transcript_mode: str = Field(
        default="native",
        alias="SUPADATA_TRANSCRIPT_MODE",
        pattern="^(native|auto|generate)$",
    )
    supadata_transcript_timeout_seconds: int = Field(
        default=60,
        alias="SUPADATA_TRANSCRIPT_TIMEOUT_SECONDS",
        ge=10,
        le=300,
    )
    apify_api_token: str | None = Field(default=None, alias="APIFY_API_TOKEN")
    apify_youtube_transcript_actor: str = Field(
        default="abotapi/youtube-transcript-scraper",
        alias="APIFY_YOUTUBE_TRANSCRIPT_ACTOR",
    )
    apify_youtube_transcript_input_style: str = Field(
        default="videoUrls",
        alias="APIFY_YOUTUBE_TRANSCRIPT_INPUT_STYLE",
    )
    apify_youtube_transcript_timeout_seconds: int = Field(
        default=120,
        alias="APIFY_YOUTUBE_TRANSCRIPT_TIMEOUT_SECONDS",
    )
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    evidence_cache_max_age_seconds: int = Field(default=86400, alias="EVIDENCE_CACHE_MAX_AGE_SECONDS", ge=300, le=2592000)

    transcript_language: str = Field(default="multi", alias="TRANSCRIPT_LANGUAGE")
    transcript_fallback_languages: str = Field(
        default="en,hi,ta",
        alias="TRANSCRIPT_FALLBACK_LANGUAGES",
    )
    deepgram_model: str = Field(default="nova-3", alias="DEEPGRAM_MODEL")
    deepgram_detect_language: bool = Field(
        default=True,
        alias="DEEPGRAM_DETECT_LANGUAGE",
    )
    assemblyai_api_key: str | None = Field(
        default=None,
        alias="ASSEMBLYAI_API_KEY",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def transcript_fallback_language_list(self) -> list[str]:
        return [
            language.strip()
            for language in self.transcript_fallback_languages.split(",")
            if language.strip()
        ]

    @property
    def langsmith_tracing_configured(self) -> bool:
        return self.langsmith_tracing and bool(
            (self.langsmith_api_key or "").strip()
        )

    def sqlalchemy_database_url(self, *, test: bool = False) -> str | None:
        value = self.test_database_url if test else self.database_url

        if value is None or not value.strip():
            return None

        url = value.strip()
        if url.startswith("postgres://"):
            return f"postgresql+psycopg://{url.removeprefix('postgres://')}"
        if url.startswith("postgresql://"):
            return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"

        return url

    @property
    def celery_broker_url(self) -> str | None:
        return self._first_configured_url(
            self.celery_broker_url_override,
            self.redis_url,
        )

    @property
    def celery_result_backend(self) -> str | None:
        return self._first_configured_url(
            self.celery_result_backend_override,
            self.redis_url,
        )

    @staticmethod
    def _first_configured_url(*values: str | None) -> str | None:
        for value in values:
            if value is not None and value.strip():
                return value.strip()

        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
