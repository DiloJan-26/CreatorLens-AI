from app.models.video import TranscriptSegment, VideoExtractionResult, VideoMetadata
from app.services import project_service


def test_cache_miss_runs_extraction(monkeypatch) -> None:
    calls = {"extract": 0}
    result = VideoExtractionResult(
        metadata=VideoMetadata(
            platform="instagram",
            url="https://www.instagram.com/reel/ABC_123/",
            extraction_status="ready",
            transcript_available=True,
            transcript_segment_count=1,
        ),
        transcript_segments=[TranscriptSegment(segment_index=0, text="Evidence")],
    )
    monkeypatch.setattr(project_service, "get_cached_extraction", lambda *_: None)

    def extract(**_kwargs):
        calls["extract"] += 1
        return result

    monkeypatch.setattr(project_service, "_extract_url", extract)
    monkeypatch.setattr(project_service, "upsert_video_metadata", lambda **_: {"id": "item-1"})
    monkeypatch.setattr(project_service, "replace_transcript_segments", lambda **_: None)
    monkeypatch.setattr(project_service, "update_content_cache_identity", lambda *_args, **_kwargs: None)

    status = project_service._extract_and_store_platform(
        project_id="project-1",
        slot="content_2",
        platform="instagram",
        url="https://www.instagram.com/reel/ABC_123/",
    )

    assert status == "ready"
    assert calls["extract"] == 1


def test_hash_mismatch_is_a_cache_miss(monkeypatch) -> None:
    result = VideoExtractionResult(
        metadata=VideoMetadata(
            platform="youtube",
            url="https://youtu.be/AbC_123-xYz",
            extraction_status="ready",
            transcript_available=True,
            transcript_segment_count=1,
        ),
        transcript_segments=[TranscriptSegment(segment_index=0, text="Evidence")],
    )
    monkeypatch.setattr(
        project_service,
        "get_cached_extraction",
        lambda *_: {
            "content_item_id": "item-1",
            "content_hash": "invalid",
            "metadata_hash": "invalid",
            "transcript_hash": "invalid",
            "metadata": result.metadata.model_dump(mode="json"),
            "segments": [segment.model_dump(mode="json") for segment in result.transcript_segments],
        },
    )

    assert (
        project_service._cached_extraction_result(
            "https://www.youtube.com/watch?v=AbC_123-xYz"
        )
        is None
    )
