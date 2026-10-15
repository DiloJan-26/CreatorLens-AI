from app.core.config import get_settings
from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata
from app.rag import indexing_service
from app.services import project_service
from app.services.hash_service import hash_embedding


def test_repeated_url_reuses_extraction_and_index(monkeypatch) -> None:
    extraction_calls = 0
    persisted: dict[str, object] = {}
    result = VideoExtractionResult(
        metadata=VideoMetadata(
            platform="youtube",
            url="https://youtu.be/AbC_123-xYz",
            title="Reusable evidence",
            extraction_status="ready",
            transcript_available=True,
            transcript_segment_count=1,
        ),
        transcript_segments=[TranscriptSegment(segment_index=0, text="Evidence")],
    )

    def cached(_normalized_url: str):
        if "hashes" not in persisted:
            return None
        content_hash, metadata_hash, transcript_hash = persisted["hashes"]
        return {
            "content_item_id": "item-1",
            "content_hash": content_hash,
            "metadata_hash": metadata_hash,
            "transcript_hash": transcript_hash,
            "metadata": result.metadata.model_dump(mode="json"),
            "segments": [
                segment.model_dump(mode="json")
                for segment in result.transcript_segments
            ],
        }

    def extract(**_kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        return result.model_copy(deep=True)

    monkeypatch.setattr(project_service, "get_cached_extraction", cached)
    monkeypatch.setattr(project_service, "_extract_url", extract)
    monkeypatch.setattr(
        project_service,
        "upsert_video_metadata",
        lambda **_: {"id": "item-1"},
    )
    monkeypatch.setattr(project_service, "replace_transcript_segments", lambda **_: None)
    monkeypatch.setattr(
        project_service,
        "update_content_cache_identity",
        lambda _item_id, **hashes: persisted.update(
            {"hashes": (hashes["content_hash"], hashes["metadata_hash"], hashes["transcript_hash"])}
        ),
    )

    for _ in range(2):
        project_service._extract_and_store_platform(
            project_id="project-1",
            slot="content_1",
            platform="youtube",
            url="https://www.youtube.com/watch?v=AbC_123-xYz",
        )

    assert extraction_calls == 1

    settings = get_settings()
    chunk_hash = "a" * 64
    chunk = {
        "chunk_id": "chunk-1",
        "project_id": "project-1",
        "content_id": "item-1",
        "slot": "content_1",
        "platform": "youtube",
        "source_type": "transcript",
        "chunk_index": 0,
        "text": "Evidence",
        "content_hash": "b" * 64,
        "chunk_hash": chunk_hash,
        "embedding_hash": hash_embedding(
            chunk_hash=chunk_hash,
            model_name=settings.embedding_model_name,
            model_version=settings.embedding_model_version,
        ),
        "citation_label": "Content 1",
        "qdrant_point_id": "point-1",
        "embedding_model_name": settings.embedding_model_name,
        "embedding_model_version": settings.embedding_model_version,
    }
    qdrant_upserts = 0
    monkeypatch.setattr(indexing_service, "get_project_record", lambda *_: {"id": "project-1"})
    monkeypatch.setattr(indexing_service, "get_rag_chunks", lambda **_: [chunk])
    monkeypatch.setattr(indexing_service, "is_qdrant_configured", lambda: True)
    monkeypatch.setattr(indexing_service, "qdrant_points_exist", lambda *_: True)
    monkeypatch.setattr(
        indexing_service,
        "embed_texts",
        lambda *_: (_ for _ in ()).throw(AssertionError("embedding was repeated")),
    )

    def upsert(**_kwargs):
        nonlocal qdrant_upserts
        qdrant_upserts += 1
        return ["point-1"]

    monkeypatch.setattr(indexing_service, "upsert_chunk_vectors", upsert)
    indexed = indexing_service.index_project("project-1", rebuild_chunks=False)

    assert indexed.status == "indexed"
    assert qdrant_upserts == 0
