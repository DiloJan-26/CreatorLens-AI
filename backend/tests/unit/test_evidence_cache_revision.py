from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.video import TranscriptSegment, VideoMetadata, VideoExtractionResult
from app.services import project_service, evidence_quality
from app.rag import chunk_builder, indexing_service
from app.rag.hybrid_search import build_hybrid_candidates
from app.services.evidence_quality import validate_extraction


def cached_payload():
    result = validate_extraction(VideoExtractionResult(metadata=VideoMetadata(platform="youtube",
        url="https://youtu.be/synthetic", duration_seconds=8, transcript_language="en",
        transcript_source="platform_captions", extraction_status="ready", transcript_evidence={"provenance": {
            "original_audio_language": "en", "caption_track_language": "en", "caption_kind": "original"}}),
        transcript_segments=[TranscriptSegment(segment_index=0, start_time=0, end_time=8, text="Original source")]))
    a, b, c = project_service._cache_hashes(result)
    return dict(metadata=result.metadata.model_dump(mode="json"), segments=[s.model_dump(mode="json") for s in result.transcript_segments],
                content_hash=a, metadata_hash=b, transcript_hash=c)


def test_compatible_valid_cache_reuses_without_provider(monkeypatch):
    cached = cached_payload()
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda _: cached)
    result = project_service._cached_extraction_result("synthetic")
    assert result is not None and result.metadata.transcript_evidence["status"] == "valid"


def test_expired_cache_and_known_invalid_cache_are_not_reused(monkeypatch):
    cached = cached_payload()
    cached["metadata"]["transcript_evidence"]["extracted_at"] = (datetime.now(UTC)-timedelta(days=2)).isoformat()
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda _: cached)
    assert project_service._cached_extraction_result("synthetic") is None
    cached = cached_payload()
    cached["metadata"]["transcript_evidence"]["status"] = "invalid"
    assert project_service._cached_extraction_result("synthetic") is None


def test_new_quality_policy_revalidates_raw_cache_locally(monkeypatch):
    cached = cached_payload()
    old = cached["metadata"]["transcript_evidence"]["revision"]
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda _: cached)
    monkeypatch.setattr(evidence_quality, "EVIDENCE_POLICY_VERSION", "synthetic-policy-next")
    result = project_service._cached_extraction_result("synthetic")
    assert result is not None
    assert result.metadata.transcript_evidence["revision"] != old


def test_same_text_with_changed_revision_does_not_reuse_embedding_identity():
    base = dict(project_id="project", content_id="item", slot="content_1", platform="youtube", source_type="transcript",
                chunk_index=0, text="Same source words", citation_label="Content 1")
    old = chunk_builder._make_chunk(**base, evidence_revision="a"*64)
    new = chunk_builder._make_chunk(**base, evidence_revision="b"*64)
    assert old.chunk_hash == new.chunk_hash
    assert old.embedding_hash != new.embedding_hash
    assert old.chunk_id != new.chunk_id
    other_slot = chunk_builder._make_chunk(**dict(base, slot="content_2"), evidence_revision="b"*64)
    assert new.chunk_id != other_slot.chunk_id


def test_stale_semantic_point_does_not_attach_by_slot_location():
    record = dict(chunk_id="new", content_id="item", slot="content_1", platform="youtube", source_type="hook",
                  chunk_index=0, citation_label="Current source", text="fresh")
    stale = dict(record, chunk_id="old", text="stale")
    candidates = build_hybrid_candidates("fresh", [record], [{"payload": stale, "score": 1.0}])
    assert candidates[0].semantic_score == 0


def test_failed_upsert_never_deletes_existing_points(monkeypatch):
    chunk = chunk_builder._make_chunk(project_id="project", content_id="item", slot="content_1", platform="youtube",
        source_type="transcript", chunk_index=0, text="source", citation_label="Content 1", evidence_revision="a"*64)
    monkeypatch.setattr(indexing_service, "get_project_record", lambda _: {})
    monkeypatch.setattr(indexing_service, "get_rag_chunks", lambda **_: [chunk.model_dump()])
    monkeypatch.setattr(indexing_service, "is_qdrant_configured", lambda: True)
    monkeypatch.setattr(indexing_service, "_reusable_vectors", lambda _: None)
    monkeypatch.setattr(indexing_service, "embed_texts", lambda _: [[0.1, 0.2]])
    monkeypatch.setattr(indexing_service, "ensure_qdrant_collection", lambda _: None)
    monkeypatch.setattr(indexing_service, "upsert_chunk_vectors", lambda **_: (_ for _ in ()).throw(RuntimeError("synthetic upsert failure")))
    monkeypatch.setattr(indexing_service, "delete_project_points", lambda *_: (_ for _ in ()).throw(AssertionError("must not delete before upsert")))
    assert indexing_service.index_project("project", rebuild_chunks=False).status == "failed"


def test_explicit_refresh_is_bounded_and_invalidates_local_evidence_first(monkeypatch):
    cached = cached_payload()
    events = []
    result = VideoExtractionResult(metadata=VideoMetadata.model_validate(cached["metadata"]),
                                   transcript_segments=[TranscriptSegment.model_validate(s) for s in cached["segments"]])
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda _: (_ for _ in ()).throw(AssertionError("refresh must bypass cache")))
    monkeypatch.setattr(project_service, "_extract_url", lambda **_: result)
    monkeypatch.setattr(project_service, "get_video_by_project_slot", lambda *_: {"transcript_evidence": {"revision": "old"}})
    monkeypatch.setattr(project_service, "replace_rag_chunks", lambda **_: events.append("invalidate"))
    monkeypatch.setattr(project_service, "upsert_video_metadata", lambda **_: events.append("metadata") or {"id": "item"})
    monkeypatch.setattr(project_service, "replace_transcript_segments", lambda **_: events.append("transcript"))
    monkeypatch.setattr(project_service, "update_content_cache_identity", lambda *_, **__: None)
    monkeypatch.setattr(project_service, "update_content_cache_observation", lambda *_, **__: None)
    status = project_service._extract_and_store_platform("project", "content_1", "youtube", "https://youtu.be/synthetic", refresh_evidence=True)
    assert status == "ready"
    assert events == ["invalidate", "metadata", "transcript"]


def test_legacy_hash_cache_is_revalidated_without_claiming_verified_language(monkeypatch):
    from app.services.hash_service import hash_metadata, hash_transcript, hash_content
    result = VideoExtractionResult(metadata=VideoMetadata(platform="youtube", url="https://youtu.be/legacy", extraction_status="ready", transcript_available=True),
        transcript_segments=[TranscriptSegment(segment_index=0, start_time=0, end_time=4, text="Legacy source")])
    payload = result.metadata.model_dump(mode="json", exclude={"slot","url","transcript_available","transcript_segment_count","transcript_language","detected_language","language_confidence","transcript_source","transcript_source_note","transcript_evidence"})
    metadata_hash = hash_metadata(payload)
    transcript_hash = hash_transcript([s.model_dump(mode="json") for s in result.transcript_segments])
    cache = dict(metadata=result.metadata.model_dump(), segments=[s.model_dump() for s in result.transcript_segments], metadata_hash=metadata_hash,
                 transcript_hash=transcript_hash, content_hash=hash_content(metadata_hash=metadata_hash, transcript_hash=transcript_hash))
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda _: cache)
    checked = project_service._cached_extraction_result("legacy")
    assert checked is not None
    assert checked.metadata.transcript_evidence["status"] == "partial"
    assert checked.metadata.transcript_evidence["provenance"]["audio_language_verified"] is False
    assert checked.metadata.transcript_evidence["cache_age_unknown"] is True


def test_unbound_verified_legacy_record_is_compatible_for_single_slot():
    from app.models.metrics import MetricSourceRecord
    from app.services.metric_source_service import _latest_matching
    common = dict(project_id="p", platform="youtube", source_platform="youtube", metric_scope="native",
                  confidence="medium", created_at="2026-11-11", updated_at="2026-11-11")
    verified = MetricSourceRecord(id="legacy", source_method="user_verified", views=42, **common)
    public = MetricSourceRecord(id="bound", source_method="public_extractor", slot="content_1", views=10, **common)
    assert _latest_matching([public, verified], "youtube", "native").id == "legacy"
    second = public.model_copy(update={"id": "second", "slot": "content_2"})
    assert _latest_matching([public, second, verified], "youtube", "native") is None
