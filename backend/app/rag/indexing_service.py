from app.core.config import get_settings
from app.models.rag import IndexProjectResponse, RagChunk
from app.rag.chunk_builder import build_project_chunks
from app.services.embedding_service import embed_texts
from app.services.qdrant_service import (
    QdrantCollectionError,
    QdrantConfigurationError,
    delete_project_points,
    ensure_qdrant_collection,
    is_qdrant_configured,
    upsert_chunk_vectors,
)
from app.services.storage_service import (
    get_project_record,
    replace_rag_chunks,
    update_rag_chunk_qdrant_point_id,
)


class ProjectIndexingNotFoundError(Exception):
    """Raised when a project cannot be found for indexing."""


def index_project(project_id: str) -> IndexProjectResponse:
    settings = get_settings()

    if get_project_record(project_id) is None:
        raise ProjectIndexingNotFoundError("Project not found.")

    chunks = build_project_chunks(project_id)
    replace_rag_chunks(project_id=project_id, chunks=chunks)

    if not chunks:
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message="No extracted content data found to index.",
        )

    if not is_qdrant_configured():
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message="Qdrant is not configured.",
        )

    try:
        vectors = embed_texts([chunk.text for chunk in chunks])
    except Exception:
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message="Could not load embedding model or embed chunks.",
        )

    vector_size = _vector_size(vectors)

    if vector_size is None:
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message="Embedding service returned no usable vectors.",
        )

    try:
        ensure_qdrant_collection(vector_size)
        delete_project_points(project_id)
        qdrant_point_ids = upsert_chunk_vectors(chunks=chunks, vectors=vectors)
    except (QdrantCollectionError, QdrantConfigurationError) as exc:
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message=str(exc),
        )
    except Exception as exc:
        return _failed_response(
            project_id=project_id,
            chunks=chunks,
            message=f"Qdrant upsert failed: {_safe_error_message(exc)}",
        )

    for chunk, qdrant_point_id in zip(chunks, qdrant_point_ids, strict=True):
        update_rag_chunk_qdrant_point_id(
            chunk_id=chunk.chunk_id,
            qdrant_point_id=qdrant_point_id,
        )

    return IndexProjectResponse(
        project_id=project_id,
        status="indexed",
        embedding_model=settings.embedding_model_name,
        qdrant_collection=settings.qdrant_collection,
        total_chunks=len(chunks),
        youtube_chunks=_platform_count(chunks, "youtube"),
        instagram_chunks=_platform_count(chunks, "instagram"),
        facebook_chunks=_platform_count(chunks, "facebook"),
        chunks_by_platform=_counts_by_field(chunks, "platform"),
        chunks_by_slot=_counts_by_field(chunks, "slot"),
        chunks_by_source_type=_counts_by_field(chunks, "source_type"),
        content_chunk_counts=_content_chunk_counts(chunks),
        message="Project chunks indexed in Qdrant.",
    )


def _failed_response(
    project_id: str,
    chunks: list[RagChunk],
    message: str,
) -> IndexProjectResponse:
    settings = get_settings()

    return IndexProjectResponse(
        project_id=project_id,
        status="failed",
        embedding_model=settings.embedding_model_name,
        qdrant_collection=settings.qdrant_collection,
        total_chunks=len(chunks),
        youtube_chunks=_platform_count(chunks, "youtube"),
        instagram_chunks=_platform_count(chunks, "instagram"),
        facebook_chunks=_platform_count(chunks, "facebook"),
        chunks_by_platform=_counts_by_field(chunks, "platform"),
        chunks_by_slot=_counts_by_field(chunks, "slot"),
        chunks_by_source_type=_counts_by_field(chunks, "source_type"),
        content_chunk_counts=_content_chunk_counts(chunks),
        message=message,
    )


def _platform_count(chunks: list[RagChunk], platform: str) -> int:
    return sum(1 for chunk in chunks if chunk.platform == platform)


def _counts_by_field(chunks: list[RagChunk], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for chunk in chunks:
        value = getattr(chunk, field_name, None)

        if value is None:
            continue

        key = str(value)
        counts[key] = counts.get(key, 0) + 1

    return dict(sorted(counts.items()))


def _content_chunk_counts(chunks: list[RagChunk]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str], int] = {}

    for chunk in chunks:
        slot = str(chunk.slot or "content")
        platform = str(chunk.platform)
        key = (slot, platform)
        counts[key] = counts.get(key, 0) + 1

    return [
        {
            "slot": slot,
            "label": _slot_label(slot),
            "platform": platform,
            "chunks": count,
        }
        for (slot, platform), count in sorted(
            counts.items(),
            key=lambda item: (_slot_sort_key(item[0][0]), item[0][1]),
        )
    ]


def _slot_label(slot: str) -> str:
    if slot == "content_1":
        return "Content 1"

    if slot == "content_2":
        return "Content 2"

    return "Content"


def _slot_sort_key(slot: str) -> int:
    if slot == "content_1":
        return 0

    if slot == "content_2":
        return 1

    return 2


def _vector_size(vectors: list[list[float]]) -> int | None:
    if not vectors or not vectors[0]:
        return None

    return len(vectors[0])


def _safe_error_message(exc: Exception) -> str:
    settings = get_settings()
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    clean_message = message or "Unknown Qdrant error."

    for secret_value in (settings.qdrant_api_key, settings.qdrant_url):
        if secret_value and secret_value in clean_message:
            clean_message = clean_message.replace(secret_value, "[redacted]")

    return clean_message[:240]
