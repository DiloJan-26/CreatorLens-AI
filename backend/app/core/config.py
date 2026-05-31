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

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    qdrant_url: str = Field(default="", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="creatorlens_chunks",
        alias="QDRANT_COLLECTION",
    )

    apify_api_token: str = Field(default="", alias="APIFY_API_TOKEN")
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    assemblyai_api_key: str = Field(default="", alias="ASSEMBLYAI_API_KEY")

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
