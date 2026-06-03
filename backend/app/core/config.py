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

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(
        default=1200,
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

    apify_api_token: str | None = Field(default=None, alias="APIFY_API_TOKEN")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
