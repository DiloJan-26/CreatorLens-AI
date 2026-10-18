from types import SimpleNamespace

from app.extractors import youtube_extractor
from app.models.video import TranscriptSegment
from app.services.transcription_service import TranscriptionResult


def test_supadata_configuration_prevents_apify_actor_calls(monkeypatch) -> None:
    monkeypatch.setattr(
        youtube_extractor,
        "get_settings",
        lambda: SimpleNamespace(
            youtube_api_key="youtube-key",
            supadata_api_key="supadata-key",
        ),
    )
    monkeypatch.setattr(
        youtube_extractor,
        "fetch_youtube_info_from_api",
        lambda _video_id, _api_key: {
            "title": "Example",
            "duration": 10,
            "webpage_url": "https://www.youtube.com/watch?v=example",
        },
    )
    monkeypatch.setattr(
        youtube_extractor,
        "fetch_youtube_transcript_with_metadata",
        lambda _video_id: TranscriptionResult(segments=[]),
    )
    monkeypatch.setattr(
        youtube_extractor,
        "transcribe_video_url_with_supadata",
        lambda _url: TranscriptionResult(
            segments=[
                TranscriptSegment(
                    segment_index=0,
                    start_time=0.0,
                    end_time=10.0,
                    text="Complete transcript",
                )
            ],
            transcript_language="en",
            transcript_source="supadata_platform_captions",
        ),
    )

    def unexpected_apify_call(_url: str) -> TranscriptionResult:
        raise AssertionError("Apify must not run when Supadata is configured.")

    monkeypatch.setattr(
        youtube_extractor,
        "transcribe_youtube_url_with_apify",
        unexpected_apify_call,
    )

    result = youtube_extractor.extract_youtube_video(
        "https://www.youtube.com/watch?v=example"
    )

    assert result.metadata.extraction_status == "ready"
    assert result.metadata.transcript_source == "supadata_platform_captions"
    assert len(result.transcript_segments) == 1
