from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata
from app.rag import indexing_service
from app.services import project_service


def _extraction_result() -> VideoExtractionResult:
    return VideoExtractionResult(
        metadata=VideoMetadata(
            platform="youtube",
            url="https://youtu.be/AbC_123-xYz",
            title="Cached title",
            extraction_status="ready",
            transcript_available=True,
            transcript_segment_count=1,
        ),
        transcript_segments=[
            TranscriptSegment(segment_index=0, start_time=0, end_time=2, text="Evidence")
        ],
    )


def test_valid_cache_hit_skips_extraction(monkeypatch) -> None:
    result = _extraction_result()
    content_hash, metadata_hash, transcript_hash = project_service._cache_hashes(result)
    cached = {
        "content_item_id": "cached-item",
        "content_hash": content_hash,
        "metadata_hash": metadata_hash,
        "transcript_hash": transcript_hash,
        "metadata": result.metadata.model_dump(mode="json"),
        "segments": [segment.model_dump(mode="json") for segment in result.transcript_segments],
    }
    stored: dict[str, object] = {}
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda *_: cached)
    monkeypatch.setattr(
        project_service,
        "_extract_url",
        lambda **_: (_ for _ in ()).throw(AssertionError("extractor was called")),
    )
    monkeypatch.setattr(
        project_service,
        "upsert_video_metadata",
        lambda **kwargs: stored.update(kwargs) or {"id": "new-item"},
    )
    monkeypatch.setattr(project_service, "replace_transcript_segments", lambda **_: None)
    monkeypatch.setattr(project_service, "update_content_cache_identity", lambda *_args, **_kwargs: None)

    status = project_service._extract_and_store_platform(
        project_id="project-2",
        slot="content_1",
        platform="youtube",
        url="https://www.youtube.com/watch?v=AbC_123-xYz&utm_source=test",
    )

    assert status == "ready"
    assert stored["normalized_url"] == "https://www.youtube.com/watch?v=AbC_123-xYz"


def test_compatible_embedding_cache_skips_embedding_and_qdrant(monkeypatch) -> None:
    chunk_hash = "a" * 64
    from app.core.config import get_settings
    from app.services.hash_service import hash_embedding

    settings = get_settings()
    embedding_hash = hash_embedding(
        chunk_hash=chunk_hash,
        model_name=settings.embedding_model_name,
        model_version=settings.embedding_model_version,
    )
    record = {
        "chunk_id": "chunk-1",
        "project_id": "project-1",
        "content_id": "content-1",
        "slot": "content_1",
        "platform": "youtube",
        "source_type": "transcript",
        "chunk_index": 0,
        "text": "Evidence",
        "content_hash": "c" * 64,
        "chunk_hash": chunk_hash,
        "embedding_hash": embedding_hash,
        "citation_label": "Content 1",
        "qdrant_point_id": "point-1",
        "embedding_model_name": settings.embedding_model_name,
        "embedding_model_version": settings.embedding_model_version,
    }
    monkeypatch.setattr(indexing_service, "get_project_record", lambda *_: {"id": "project-1"})
    monkeypatch.setattr(indexing_service, "get_rag_chunks", lambda **_: [record])
    monkeypatch.setattr(indexing_service, "is_qdrant_configured", lambda: True)
    monkeypatch.setattr(indexing_service, "qdrant_points_exist", lambda *_: True)
    monkeypatch.setattr(
        indexing_service,
        "embed_texts",
        lambda *_: (_ for _ in ()).throw(AssertionError("embedding was called")),
    )
    monkeypatch.setattr(
        indexing_service,
        "upsert_chunk_vectors",
        lambda **_: (_ for _ in ()).throw(AssertionError("Qdrant upsert was called")),
    )

    response = indexing_service.index_project("project-1", rebuild_chunks=False)

    assert response.status == "indexed"
    assert "reused" in str(response.message).lower()


def test_cached_vector_skips_embedding_for_a_new_project(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.hash_service import hash_embedding

    settings = get_settings()
    chunk_hash = "d" * 64
    embedding_hash = hash_embedding(
        chunk_hash=chunk_hash,
        model_name=settings.embedding_model_name,
        model_version=settings.embedding_model_version,
    )
    record = {
        "chunk_id": "new-chunk",
        "project_id": "new-project",
        "content_id": "new-content",
        "slot": "content_1",
        "platform": "youtube",
        "source_type": "transcript",
        "chunk_index": 0,
        "text": "Evidence",
        "content_hash": "e" * 64,
        "chunk_hash": chunk_hash,
        "embedding_hash": embedding_hash,
        "citation_label": "Content 1",
        "qdrant_point_id": None,
        "embedding_model_name": settings.embedding_model_name,
        "embedding_model_version": settings.embedding_model_version,
    }
    captured_vectors: list[list[float]] = []
    monkeypatch.setattr(indexing_service, "get_project_record", lambda *_: {"id": "new-project"})
    monkeypatch.setattr(indexing_service, "get_rag_chunks", lambda **_: [record])
    monkeypatch.setattr(indexing_service, "is_qdrant_configured", lambda: True)
    monkeypatch.setattr(
        indexing_service,
        "get_reusable_qdrant_point_ids",
        lambda *_: {embedding_hash: "source-point"},
    )
    monkeypatch.setattr(
        indexing_service,
        "get_point_vectors",
        lambda *_: {"source-point": [0.1, 0.2]},
    )
    monkeypatch.setattr(
        indexing_service,
        "embed_texts",
        lambda *_: (_ for _ in ()).throw(AssertionError("embedding was called")),
    )
    monkeypatch.setattr(indexing_service, "ensure_qdrant_collection", lambda *_: None)
    monkeypatch.setattr(indexing_service, "delete_project_points", lambda *_: None)

    def upsert(*, chunks, vectors):
        assert len(chunks) == 1
        captured_vectors.extend(vectors)
        return ["new-point"]

    monkeypatch.setattr(indexing_service, "upsert_chunk_vectors", upsert)
    monkeypatch.setattr(indexing_service, "update_rag_chunk_qdrant_point_id", lambda **_: None)

    response = indexing_service.index_project("new-project", rebuild_chunks=False)

    assert response.status == "indexed"
    assert captured_vectors == [[0.1, 0.2]]
