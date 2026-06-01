from fastapi import APIRouter
from qdrant_client import QdrantClient

from app.core.config import get_settings


router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "creatorlens-api",
        "environment": settings.environment,
    }


@router.get("/health/qdrant")
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
