from typing import Literal
from decimal import Decimal
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

    youtube_metadata_enrichment_enabled: bool = Field(default=True, alias="YOUTUBE_METADATA_ENRICHMENT_ENABLED")
    youtube_enrichment_daily_units: int = Field(default=100, alias="YOUTUBE_ENRICHMENT_DAILY_UNITS", ge=1, le=10000)
    service_role: Literal["web", "worker"] = Field(default="web", alias="SERVICE_ROLE")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    provider_emergency_stop: bool = Field(default=True, alias="PROVIDER_EMERGENCY_STOP")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_jwt_issuer: str | None = Field(default=None, alias="SUPABASE_JWT_ISSUER")
    supabase_jwks_url: str | None = Field(default=None, alias="SUPABASE_JWKS_URL")
    supabase_jwt_audience: str = Field(default="authenticated", alias="SUPABASE_JWT_AUDIENCE")
    authenticated_requests_per_minute: int = Field(default=120, alias="AUTHENTICATED_REQUESTS_PER_MINUTE", ge=0)
    analysis_requests_per_minute: int = Field(default=2, alias="ANALYSIS_REQUESTS_PER_MINUTE", ge=0)
    paid_requests_per_minute: int = Field(default=12, alias="PAID_REQUESTS_PER_MINUTE", ge=0)
    provider_input_byte_limit: int = Field(default=65536, alias="PROVIDER_INPUT_BYTE_LIMIT", ge=0, le=131072)
    user_budget_usd: Decimal = Field(default=Decimal("0.50"), alias="USER_BUDGET_USD", ge=0, max_digits=24, decimal_places=12)
    global_budget_usd: Decimal = Field(default=Decimal("2.00"), alias="GLOBAL_BUDGET_USD", ge=0, max_digits=24, decimal_places=12)
    provider_operation_ceiling_usd: Decimal = Field(default=Decimal("0.05"), alias="PROVIDER_OPERATION_CEILING_USD", ge=0, max_digits=24, decimal_places=12)

    extraction_max_concurrent_operations: int = Field(default=1, alias="EXTRACTION_MAX_CONCURRENT_OPERATIONS", ge=0, le=16)
    extraction_max_video_seconds: int = Field(default=300, alias="EXTRACTION_MAX_VIDEO_SECONDS", ge=0, le=86400)
    extraction_max_url_bytes: int = Field(default=2048, alias="EXTRACTION_MAX_URL_BYTES", ge=0, le=8192)
    extraction_max_response_bytes: int = Field(default=2097152, alias="EXTRACTION_MAX_RESPONSE_BYTES", ge=0, le=16777216)
    extraction_timeout_seconds: int = Field(default=30, alias="EXTRACTION_TIMEOUT_SECONDS", ge=0, le=120)
    # Legacy/optional reporting metadata only; never required to admit extraction.
    supadata_billing_tier: str = Field(default="", alias="SUPADATA_BILLING_TIER")
    supadata_prepaid_verified: bool = Field(default=False, alias="SUPADATA_PREPAID_VERIFIED")
    supadata_auto_recharge_disabled: bool = Field(default=False, alias="SUPADATA_AUTO_RECHARGE_DISABLED")
    supadata_credit_pool: str = Field(default="", alias="SUPADATA_CREDIT_POOL")
    supadata_credit_pool_cap: int = Field(default=100, alias="SUPADATA_CREDIT_POOL_CAP", ge=1, le=3000)
    supadata_credit_limit: int = Field(default=0, alias="SUPADATA_CREDIT_LIMIT", ge=0, le=3000)

    # Operational allowances; stored grants and historical money are never rewritten.
    initial_free_analyses: int = Field(default=5, alias="INITIAL_FREE_ANALYSES", ge=0, le=10000)
    concurrent_analyses_per_user: int = Field(default=1, alias="CONCURRENT_ANALYSES_PER_USER", ge=1, le=16)
    assistant_admissions_per_analysis: int = Field(default=3, alias="ASSISTANT_ADMISSIONS_PER_ANALYSIS", ge=0, le=100)
    semantic_attempts_per_slot: int = Field(default=2, alias="SEMANTIC_ATTEMPTS_PER_SLOT", ge=0, le=10)
    extraction_metadata_attempts_per_slot: int = Field(default=1, alias="EXTRACTION_METADATA_ATTEMPTS_PER_SLOT", ge=1, le=10)
    extraction_transcript_attempts_per_slot: int = Field(default=2, alias="EXTRACTION_TRANSCRIPT_ATTEMPTS_PER_SLOT", ge=1, le=10)
    supadata_request_interval_ms: int = Field(default=1100, alias="SUPADATA_REQUEST_INTERVAL_MS", ge=100, le=60000)
    redis_request_timeout_seconds: int = Field(default=2, alias="REDIS_REQUEST_TIMEOUT_SECONDS", ge=1, le=30)
    provider_schema_token_allowance: int = Field(default=2048, alias="PROVIDER_SCHEMA_TOKEN_ALLOWANCE", ge=2048, le=16384)
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS", ge=1, le=65)
    assistant_max_output_tokens: int = Field(default=2400, alias="ASSISTANT_MAX_OUTPUT_TOKENS", ge=1, le=8192)
    semantic_max_output_tokens: int = Field(default=4096, alias="SEMANTIC_MAX_OUTPUT_TOKENS", ge=1, le=8192)
    semantic_timeout_seconds: int = Field(default=60, alias="SEMANTIC_TIMEOUT_SECONDS", ge=1, le=65)
    inference_deadline_grace_seconds: int = Field(default=5, alias="INFERENCE_DEADLINE_GRACE_SECONDS", ge=1, le=30)
    diagnostic_max_output_tokens: int = Field(default=80, alias="DIAGNOSTIC_MAX_OUTPUT_TOKENS", ge=1, le=8192)
    llm_active_pricing_json: str | None = Field(default=None, alias="LLM_ACTIVE_PRICING_JSON", repr=False)
    extraction_active_pricing_json: str | None = Field(default=None, alias="EXTRACTION_ACTIVE_PRICING_JSON", repr=False)
    celery_queue: str = Field(default="creatorlens", alias="CELERY_QUEUE", pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    celery_worker_concurrency: int = Field(default=1, alias="CELERY_WORKER_CONCURRENCY", ge=1, le=1)
    celery_prefetch_multiplier: int = Field(default=1, alias="CELERY_PREFETCH_MULTIPLIER", ge=1, le=16)
    celery_broker_pool_limit: int = Field(default=2, alias="CELERY_BROKER_POOL_LIMIT", ge=1, le=20)
    celery_publish_max_retries: int = Field(default=2, alias="CELERY_PUBLISH_MAX_RETRIES", ge=0, le=5)
    outbox_batch_size: int = Field(default=20, alias="OUTBOX_BATCH_SIZE", ge=1, le=1000)
    outbox_max_attempts: int = Field(default=5, alias="OUTBOX_MAX_ATTEMPTS", ge=1, le=100)
    reconciliation_after_seconds: int = Field(default=600, alias="RECONCILIATION_AFTER_SECONDS", ge=600, le=604800)
    reconciliation_batch_size: int = Field(default=100, alias="RECONCILIATION_BATCH_SIZE", ge=1, le=1000)
    youtube_metadata_timeout_seconds: int = Field(default=15, alias="YOUTUBE_METADATA_TIMEOUT_SECONDS", ge=1, le=120)
    youtube_channel_timeout_seconds: int = Field(default=10, alias="YOUTUBE_CHANNEL_TIMEOUT_SECONDS", ge=1, le=120)
    deepgram_timeout_seconds: int = Field(default=45, alias="DEEPGRAM_TIMEOUT_SECONDS", ge=1, le=300)
    supadata_poll_interval_seconds: float = Field(default=1, alias="SUPADATA_POLL_INTERVAL_SECONDS", ge=.1, le=30)
    http_connect_timeout_seconds: int = Field(default=10, alias="HTTP_CONNECT_TIMEOUT_SECONDS", ge=1, le=60)
    apify_transport_grace_seconds: int = Field(default=15, alias="APIFY_TRANSPORT_GRACE_SECONDS", ge=1, le=60)
    jwks_timeout_seconds: int = Field(default=3, alias="JWKS_TIMEOUT_SECONDS", ge=1, le=10)



    @model_validator(mode="after")
    def validate_configuration(self):
        from app.core.hosting import hosted_runtime
        from app.core.active_pricing import active_registry
        if self.llm_active_pricing_json is not None:
            active_registry(self.llm_active_pricing_json, "llm")
        if self.extraction_active_pricing_json is not None:
            active_registry(self.extraction_active_pricing_json, "extraction")
        # Pure offline algorithms may construct partial settings. This never
        # opens an HTTP/worker bypass: authentication is enforced unconditionally.
        if hosted_runtime() or self.environment not in {"local", "test"}:
            self.require_service_configuration()
        elif any((self.supabase_url,self.supabase_jwt_issuer,self.supabase_jwks_url)):
            validate_verification_configuration(self)
        return self

    def require_service_configuration(self):
        from urllib.parse import urlsplit,parse_qs
        from app.core.hosting import hosted_runtime
        if self.service_role=="web":validate_verification_configuration(self)
        if not self.database_url or not self.database_url.startswith(("postgres://","postgresql://","postgresql+psycopg://")) or not self.redis_url:
            raise ValueError("The authenticated application requires PostgreSQL and Redis.")
        if not self.authenticated_requests_per_minute:
            raise ValueError("A nonzero authenticated request limit is required.")
        if hosted_runtime() or self.environment not in {"local","test"}:
            for value in (self.redis_url,self.celery_broker_url,self.celery_result_backend):
                connection=urlsplit(value or "")
                if connection.scheme!="rediss" or not connection.hostname or any(v.lower() in {"none","optional","0","false"} for v in parse_qs(connection.query).get("ssl_cert_reqs",[])):
                    raise ValueError("Deployed services require verified TLS Redis connections.")
            database=urlsplit(self.database_url)
            modes=parse_qs(database.query).get("sslmode",[])
            if not database.hostname or not database.path.strip("/") or len(modes)!=1 or modes[0] not in {"require","verify-ca","verify-full"}:
                raise ValueError("Deployed PostgreSQL requires explicit TLS.")
            if self.service_role=="web":
                if not self.cors_origin_list:
                    raise ValueError("The API requires exact HTTPS CORS origins.")
                for origin in self.cors_origin_list:
                    parsed=urlsplit(origin)
                    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                        raise ValueError("The API requires exact HTTPS CORS origins.")
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
    celery_broker_connection_timeout_seconds: int = Field(
        default=5,
        alias="CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS",
        ge=1,
        le=30,
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    semantic_supported_languages: str = Field(default="en,hi,ta", alias="SEMANTIC_SUPPORTED_LANGUAGES")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default=DEFAULT_GEMINI_MODEL, alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.35, alias="LLM_TEMPERATURE", ge=0, le=2, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(
        default=2200,
        alias="LLM_MAX_OUTPUT_TOKENS", ge=1, le=8192,
    )
    llm_estimate_service_tier: str | None = Field(default="standard", alias="LLM_ESTIMATE_SERVICE_TIER")
    llm_cache_billing_mode: str = Field(default="implicit", alias="LLM_CACHE_BILLING_MODE")
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

    qdrant_timeout_seconds: int = Field(default=10, alias="QDRANT_TIMEOUT_SECONDS", ge=1, le=120)
    langsmith_sample_rate: float = Field(default=1.0, alias="LANGSMITH_SAMPLE_RATE", ge=0, le=1, allow_inf_nan=False)
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
        alias="APIFY_YOUTUBE_TRANSCRIPT_TIMEOUT_SECONDS", ge=1, le=300,
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


def validate_verification_configuration(settings):
    """Trusted verification identity is mandatory; never selected by token data."""
    from urllib.parse import urlsplit
    base=(getattr(settings,"supabase_url",None) or "").rstrip("/")
    parsed=urlsplit(base)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.port or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Trusted HTTPS Supabase verification configuration is required.")
    if getattr(settings,"supabase_jwt_issuer",None)!=base+"/auth/v1" or getattr(settings,"supabase_jwks_url",None)!=base+"/auth/v1/.well-known/jwks.json" or getattr(settings,"supabase_jwt_audience",None)!="authenticated":
        raise ValueError("Supabase issuer, audience and JWKS must match the trusted project.")


def setting_value(settings, name):
    """Use the central declared default for legacy structural settings adapters.

    Real Settings objects always carry every field. This does not instantiate
    settings, reread environment files or invent a second operational default.
    """
    if name not in Settings.model_fields:
        raise KeyError("Unknown operational setting.")
    return getattr(settings,name,Settings.model_fields[name].get_default())


@lru_cache
def get_settings() -> Settings:
    return Settings()
