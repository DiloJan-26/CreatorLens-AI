from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
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
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-3.5-flash", alias="LLM_MODEL")
    llm_fallback_model: str | None = Field(default=None, alias="LLM_FALLBACK_MODEL")
    llm_temperature: float = Field(default=0.35, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(
        default=2200,
        alias="LLM_MAX_OUTPUT_TOKENS",
    )
    debug_rag_prompt: bool = Field(default=False, alias="DEBUG_RAG_PROMPT")

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

    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
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
