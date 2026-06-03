import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.models.rag import RagChunk


class QdrantConfigurationError(Exception):
    """Raised when Qdrant is not configured for vector storage."""


class QdrantCollectionError(Exception):
    """Raised when the configured Qdrant collection is incompatible."""


FILTER_PAYLOAD_FIELDS = ("project_id", "slot", "platform", "source_type")


def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    qdrant_url = (settings.qdrant_url or "").strip()

    if not qdrant_url:
        raise QdrantConfigurationError("QDRANT_URL is missing.")

    return QdrantClient(
        url=qdrant_url,
        api_key=(settings.qdrant_api_key or None),
    )


def is_qdrant_configured() -> bool:
    return bool((get_settings().qdrant_url or "").strip())


def list_qdrant_collections() -> list[str]:
    client = get_qdrant_client()
    collections_response = client.get_collections()

    return [collection.name for collection in collections_response.collections]


def ensure_qdrant_collection(vector_size: int) -> None:
    if vector_size <= 0:
        raise QdrantCollectionError("Vector size must be greater than zero.")

    settings = get_settings()
    collection_name = settings.qdrant_collection
    client = get_qdrant_client()
    existing_collections = list_qdrant_collections()

    if collection_name not in existing_collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        ensure_qdrant_payload_indexes()
        return

    existing_size = _collection_vector_size(client, collection_name)

    if existing_size is None:
        raise QdrantCollectionError(
            f"Qdrant collection '{collection_name}' does not expose vector size."
        )

    if existing_size != vector_size:
        raise QdrantCollectionError(
            f"Qdrant collection '{collection_name}' has vector size "
            f"{existing_size}, but embedding model requires {vector_size}."
        )

    ensure_qdrant_payload_indexes()


def ensure_qdrant_payload_indexes() -> None:
    settings = get_settings()
    collection_name = settings.qdrant_collection
    client = get_qdrant_client()

    if collection_name not in list_qdrant_collections():
        return

    existing_indexes = _collection_payload_indexes(client, collection_name)

    for field_name in FILTER_PAYLOAD_FIELDS:
        if field_name in existing_indexes:
            continue

        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=PayloadSchemaType.KEYWORD,
            wait=True,
        )


def delete_project_points(project_id: str) -> None:
    settings = get_settings()
    collection_name = settings.qdrant_collection

    if collection_name not in list_qdrant_collections():
        return

    ensure_qdrant_payload_indexes()

    client = get_qdrant_client()
    client.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="project_id",
                        match=MatchValue(value=project_id),
                    )
                ]
            )
        ),
        wait=True,
    )


def upsert_chunk_vectors(
    chunks: list[RagChunk],
    vectors: list[list[float]],
) -> list[str]:
    if len(chunks) != len(vectors):
        raise ValueError("Chunk and vector counts must match.")

    settings = get_settings()
    collection_name = settings.qdrant_collection
    client = get_qdrant_client()
    point_ids = [make_qdrant_point_id(chunk) for chunk in chunks]

    points = [
        PointStruct(
            id=point_id,
            vector=vector,
            payload=_chunk_payload(chunk),
        )
        for chunk, vector, point_id in zip(chunks, vectors, point_ids, strict=True)
    ]

    if points:
        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

    return point_ids


def search_project_chunks(
    project_id: str,
    query_vector: list[float],
    top_k: int = 6,
    platform: str | None = None,
    slot: str | None = None,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    collection_name = settings.qdrant_collection

    if collection_name not in list_qdrant_collections():
        return []

    ensure_qdrant_payload_indexes()

    client = get_qdrant_client()
    query_filter = _project_search_filter(
        project_id=project_id,
        platform=platform,
        slot=slot,
        source_type=source_type,
    )
    safe_limit = max(1, min(top_k, 12))

    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=safe_limit,
            with_payload=True,
            with_vectors=False,
        )
        points = getattr(response, "points", [])
    else:
        points = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=safe_limit,
            with_payload=True,
            with_vectors=False,
        )

    return [_point_to_search_result(point) for point in points]


def make_qdrant_point_id(chunk: RagChunk) -> str:
    base = (
        f"{chunk.project_id}:"
        f"{chunk.content_id}:"
        f"{chunk.slot}:"
        f"{chunk.platform}:"
        f"{chunk.source_type}:"
        f"{chunk.chunk_index}:"
        f"{chunk.content_hash}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def _chunk_payload(chunk: RagChunk) -> dict[str, Any]:
    return {
        "project_id": _payload_value(chunk.project_id),
        "content_id": _payload_value(chunk.content_id),
        "slot": _payload_value(chunk.slot),
        "platform": _payload_value(chunk.platform),
        "source_type": _payload_value(chunk.source_type),
        "chunk_index": _payload_value(chunk.chunk_index),
        "start_time": _payload_value(chunk.start_time),
        "end_time": _payload_value(chunk.end_time),
        "title": _payload_value(chunk.title),
        "creator": _payload_value(chunk.creator),
        "text": _payload_text(chunk.text),
        "citation_label": _payload_value(chunk.citation_label),
        "content_hash": _payload_value(chunk.content_hash),
    }


def _payload_value(value: Any) -> str | int | float | bool | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, bool):
        return value

    if isinstance(value, int | float):
        return value

    return None


def _payload_text(value: Any) -> str:
    if isinstance(value, str):
        return value

    if value is None:
        return ""

    return str(value)


def _project_search_filter(
    project_id: str,
    platform: str | None = None,
    slot: str | None = None,
    source_type: str | None = None,
) -> Filter:
    conditions = [
        FieldCondition(
            key="project_id",
            match=MatchValue(value=project_id),
        )
    ]

    if platform is not None:
        conditions.append(
            FieldCondition(
                key="platform",
                match=MatchValue(value=platform),
            )
        )

    if slot is not None:
        conditions.append(
            FieldCondition(
                key="slot",
                match=MatchValue(value=slot),
            )
        )

    if source_type is not None:
        conditions.append(
            FieldCondition(
                key="source_type",
                match=MatchValue(value=source_type),
            )
        )

    return Filter(must=conditions)


def _point_to_search_result(point: Any) -> dict[str, Any]:
    payload = getattr(point, "payload", None)
    score = getattr(point, "score", 0.0)

    return {
        "payload": payload if isinstance(payload, dict) else {},
        "score": float(score) if isinstance(score, int | float) else 0.0,
    }


def _collection_vector_size(
    client: QdrantClient,
    collection_name: str,
) -> int | None:
    collection_info = client.get_collection(collection_name)
    vectors_config = _nested_attr(collection_info, ["config", "params", "vectors"])

    if isinstance(vectors_config, dict):
        if "size" in vectors_config:
            return _as_int(vectors_config.get("size"))

        first_vector = next(iter(vectors_config.values()), None)
        return _as_int(_nested_attr(first_vector, ["size"]))

    if isinstance(vectors_config, VectorParams):
        return _as_int(vectors_config.size)

    return _as_int(_nested_attr(vectors_config, ["size"]))


def _collection_payload_indexes(
    client: QdrantClient,
    collection_name: str,
) -> set[str]:
    collection_info = client.get_collection(collection_name)
    payload_schema = getattr(collection_info, "payload_schema", None)

    if isinstance(payload_schema, dict):
        return {str(key) for key in payload_schema}

    return set()


def _nested_attr(value: Any, keys: list[str]) -> Any:
    current = value

    for key in keys:
        if current is None:
            return None

        if isinstance(current, dict):
            current = current.get(key)
            continue

        current = getattr(current, key, None)

    return current


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    return None
