from fastapi import APIRouter

from app.core.config import get_settings
from app.models.rag import EmbeddingHealthResponse, VectorStoreHealthResponse
from app.services.embedding_service import get_embedding_dimension
from app.services.qdrant_service import (
    is_qdrant_configured,
    list_qdrant_collections,
)


router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "creatorlens-api",
        "environment": settings.environment,
    }


@router.get("/health/qdrant", response_model=VectorStoreHealthResponse)
def qdrant_health() -> VectorStoreHealthResponse:
    if not is_qdrant_configured():
        return VectorStoreHealthResponse(
            status="not_configured",
            collection=settings.qdrant_collection,
            qdrant_configured=False,
            message="QDRANT_URL is missing.",
        )

    try:
        collections = list_qdrant_collections()

        return VectorStoreHealthResponse(
            status="ok",
            collection=settings.qdrant_collection,
            qdrant_configured=True,
            collections=collections,
        )
    except Exception:
        return VectorStoreHealthResponse(
            status="error",
            collection=settings.qdrant_collection,
            qdrant_configured=True,
            message="Could not connect to Qdrant.",
        )


@router.get("/health/embeddings", response_model=EmbeddingHealthResponse)
def embeddings_health() -> EmbeddingHealthResponse:
    try:
        vector_size = get_embedding_dimension()

        return EmbeddingHealthResponse(
            status="ok",
            model_name=settings.embedding_model_name,
            vector_size=vector_size,
        )
    except Exception:
        return EmbeddingHealthResponse(
            status="error",
            model_name=settings.embedding_model_name,
            message="Could not load embedding model.",
        )
