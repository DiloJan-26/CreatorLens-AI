from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient

from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title="CreatorLens AI API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "creatorlens-api",
        "environment": settings.environment,
    }


@app.get("/health/qdrant")
def qdrant_health() -> dict[str, object]:
    if not settings.qdrant_url:
        return {
            "status": "not_configured",
            "message": "QDRANT_URL is missing.",
        }

    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        collections_response = client.get_collections()
        collections = [
            collection.name for collection in collections_response.collections
        ]

        return {
            "status": "ok",
            "collections": collections,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": "Could not connect to Qdrant.",
            "detail": str(exc)[:200],
        }
