import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.models.chat import (
    LLMGenerationTestRequest,
    LLMGenerationTestResponse,
    LLMHealthResponse,
)
from app.models.rag import EmbeddingHealthResponse, VectorStoreHealthResponse
from app.services.llm_service import (
    check_llm_configured,
    get_llm,
    run_llm_generation_test,
)
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


@router.get("/health/llm", response_model=LLMHealthResponse)
def llm_health() -> LLMHealthResponse:
    return check_llm_configured()


@router.post("/health/llm/test", response_model=LLMGenerationTestResponse)
async def llm_generation_test(
    payload: LLMGenerationTestRequest,
) -> LLMGenerationTestResponse:
    return await run_llm_generation_test(payload.prompt)


@router.post("/health/llm/stream-test")
def llm_stream_generation_test(
    payload: LLMGenerationTestRequest,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_llm_generation_test(payload.prompt),
        media_type="text/event-stream",
    )


async def _stream_llm_generation_test(prompt: str) -> AsyncIterator[str]:
    safe_prompt = prompt.strip() or (
        "In one sentence, say that Gemini is connected for CreatorLens AI."
    )

    try:
        llm = get_llm(
            streaming=True,
            temperature=0.2,
            max_output_tokens=80,
        )

        yield _sse_event(
            "trace",
            {
                "mode": "gemini_connection_test",
                "provider": settings.llm_provider,
                "model": settings.llm_model,
            },
        )

        async for chunk in llm.astream(safe_prompt):
            text = _chunk_text(chunk)

            if text:
                yield _sse_event("token", {"text": text})

        yield _sse_event("done", {"status": "complete"})
    except Exception:
        yield _sse_event(
            "error",
            {
                "message": (
                    "Gemini generation test failed. Check API key, model name, "
                    "quota, or network."
                )
            },
        )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _chunk_text(chunk: object) -> str:
    content = getattr(chunk, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])

        return "".join(parts)

    return ""
