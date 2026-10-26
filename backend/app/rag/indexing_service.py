import logging

from app.core.config import get_settings
from app.models.rag import IndexProjectResponse, RagChunk
from app.rag.chunk_builder import build_project_chunks
from app.services.embedding_service import embed_texts
from app.services.hash_service import hash_embedding
from app.services.qdrant_service import (
    QdrantCollectionError,
    QdrantConfigurationError,
    delete_project_points,
    ensure_qdrant_collection,
    get_point_vectors,
    is_qdrant_configured,
    qdrant_points_exist,
    upsert_chunk_vectors,
)
from app.services.storage_compat_service import (
    get_reusable_qdrant_point_ids,
    get_rag_chunks,
    get_project_record,
    replace_rag_chunks,
    update_rag_chunk_qdrant_point_id,
    update_project_embedding_observation,
)


class ProjectIndexingNotFoundError(Exception):
    """Raised when a project cannot be found for indexing."""


logger = logging.getLogger(__name__)


def index_project(
    project_id: str,
    *,
    rebuild_chunks: bool = True,
) -> IndexProjectResponse:
    settings = get_settings()

    if get_project_record(project_id) is None:
        raise ProjectIndexingNotFoundError("Project not found.")

    if rebuild_chunks:
        chunks = build_project_chunks(project_id)
        replace_rag_chunks(project_id=project_id, chunks=chunks)
    else:
        chunks = [
            RagChunk(**record)
            for record in get_rag_chunks(project_id=project_id)
        ]

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

    if _has_reusable_embeddings(chunks) and _stored_points_exist(chunks):
        logger.info(
            "Embedding cache hit project_id=%s total_chunks=%s; "
            "skipping embedding generation and Qdrant upsert",
            project_id,
            len(chunks),
        )
        _record_embedding_observation(project_id, reused=True)
        return _indexed_response(
            project_id=project_id,
            chunks=chunks,
            message="Existing compatible embeddings and Qdrant points reused.",
        )

    logger.info(
        "Embedding cache miss project_id=%s total_chunks=%s",
        project_id,
        len(chunks),
    )

    vectors = _reusable_vectors(chunks)
    reused_embedding_vectors = vectors is not None
    if vectors is None:
        try:
            vectors = embed_texts([chunk.text for chunk in chunks])
        except Exception:
            return _failed_response(
                project_id=project_id,
                chunks=chunks,
                message="Could not load embedding model or embed chunks.",
            )
    else:
        logger.info(
            "Embedding vectors reused project_id=%s total_chunks=%s",
            project_id,
            len(chunks),
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

    _record_embedding_observation(
        project_id,
        reused=reused_embedding_vectors,
    )

    return _indexed_response(
        project_id=project_id,
        chunks=chunks,
        message=(
            "Compatible embedding vectors reused and project points indexed."
            if reused_embedding_vectors
            else "Project chunks indexed in Qdrant."
        ),
    )


def _indexed_response(
    *, project_id: str, chunks: list[RagChunk], message: str
) -> IndexProjectResponse:
    settings = get_settings()
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
        message=message,
    )


def _has_reusable_embeddings(chunks: list[RagChunk]) -> bool:
    settings = get_settings()
    for chunk in chunks:
        if not chunk.qdrant_point_id or not chunk.chunk_hash or not chunk.embedding_hash:
            return False
        expected = hash_embedding(
            chunk_hash=chunk.chunk_hash,
            model_name=settings.embedding_model_name,
            model_version=settings.embedding_model_version,
        )
        if chunk.embedding_hash != expected:
            return False
    return bool(chunks)


def _record_embedding_observation(project_id: str, *, reused: bool) -> None:
    try:
        update_project_embedding_observation(
            project_id,
            embedding_reused=reused,
        )
    except Exception:
        logger.warning(
            "Could not persist embedding cache observation project_id=%s",
            project_id,
            exc_info=True,
        )


def _stored_points_exist(chunks: list[RagChunk]) -> bool:
    try:
        return qdrant_points_exist(
            [str(chunk.qdrant_point_id) for chunk in chunks if chunk.qdrant_point_id]
        )
    except Exception as exc:
        logger.warning(
            "Could not validate cached Qdrant points; rebuilding index "
            "exception_type=%s",
            type(exc).__name__,
        )
        return False


def _reusable_vectors(chunks: list[RagChunk]) -> list[list[float]] | None:
    embedding_hashes = [
        str(chunk.embedding_hash) for chunk in chunks if chunk.embedding_hash
    ]
    if len(embedding_hashes) != len(chunks):
        return None
    try:
        point_ids = get_reusable_qdrant_point_ids(embedding_hashes)
        if any(digest not in point_ids for digest in embedding_hashes):
            return None
        vectors_by_point = get_point_vectors(
            list(dict.fromkeys(point_ids[digest] for digest in embedding_hashes))
        )
        vectors = [
            vectors_by_point.get(point_ids[digest]) for digest in embedding_hashes
        ]
        if any(vector is None for vector in vectors):
            return None
        return [vector for vector in vectors if vector is not None]
    except Exception as exc:
        logger.warning(
            "Could not reuse cached embedding vectors; generating them again "
            "exception_type=%s",
            type(exc).__name__,
        )
        return None


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
