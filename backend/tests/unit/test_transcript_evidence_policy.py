from types import SimpleNamespace
import pytest

from app.extractors import youtube_extractor as youtube
from app.models.video import TranscriptSegment, VideoMetadata, VideoExtractionResult
from app.services.evidence_quality import assess_transcript, validate_extraction
from app.services.evidence_window import select_evidence_window


def track(language, generated=False, translated=False):
    return SimpleNamespace(language_code=language, is_generated=generated, is_translated=translated,
        fetch=lambda: [dict(text="Original source words", start=0, duration=4)])


def configure(monkeypatch, tracks):
    monkeypatch.setattr(youtube, "get_settings", lambda: SimpleNamespace(transcript_fallback_language_list=["en", "hi", "ta"]))
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", lambda: SimpleNamespace(list=lambda _: tracks))


def test_original_audio_metadata_overrides_requested_languages(monkeypatch):
    configure(monkeypatch, [track("en"), track("ta", True)])
    result = youtube.fetch_youtube_transcript_with_metadata("synthetic", "ta-IN")
    assert result.transcript_language == "ta"
    assert result.detected_language is None
    assert result.provenance["caption_kind"] == "automatic"
    assert result.provenance["audio_language_verified"] is False
    assert result.provenance["requested_languages"] == ["en", "hi", "ta"]


def test_matching_manual_preferred_to_generated(monkeypatch):
    configure(monkeypatch, [track("en", True), track("en", False)])
    result = youtube.fetch_youtube_transcript_with_metadata("synthetic", "en")
    assert result.provenance["caption_kind"] == "original"


def test_wrong_language_only_is_unavailable_not_first_track(monkeypatch):
    configure(monkeypatch, [track("ar")])
    result = youtube.fetch_youtube_transcript_with_metadata("synthetic", "en")
    assert result.segments == []
    assert result.provenance["selection_reason"] == "no_compatible_language_track"
    assert result.provenance["available_track_languages"] == ["ar"]


def test_unknown_audio_language_is_not_claimed_verified(monkeypatch):
    configure(monkeypatch, [track("en")])
    result = youtube.fetch_youtube_transcript_with_metadata("synthetic")
    assert result.provenance["original_audio_language"] is None
    assert result.provenance["audio_language_verified"] is False
    assert result.provenance["selection_reason"] == "requested_language_match_audio_unverified"


def test_translated_track_remains_marked_without_translate_call(monkeypatch):
    configure(monkeypatch, [track("en", translated=True)])
    result = youtube.fetch_youtube_transcript_with_metadata("synthetic", "en")
    assert result.provenance["caption_kind"] == "translated"
    assert result.segments[0].text == "Original source words"


@pytest.mark.parametrize("start,end,text,issue", [
    (0, 1, "  ", "empty_text"), (-1, 1, "words", "negative_or_reversed_timestamp"),
    (2, 1, "words", "negative_or_reversed_timestamp"),
    (0, None, "words", "invalid_or_incomplete_timestamp"),
    (float("nan"), 1, "words", "invalid_or_incomplete_timestamp"),
    (0, 15, "words", "beyond_video_duration"),
])
def test_invalid_segments_are_quarantined(start, end, text, issue):
    usable, quality = assess_transcript([TranscriptSegment(segment_index=0, start_time=start, end_time=end, text=text)], duration=10)
    assert usable == []
    assert quality["status"] == "invalid"
    assert issue in quality["issues"]
    assert quality["rejected_segments"][0]["text"] == text


def test_overlap_and_gaps_report_union_coverage():
    segments = [TranscriptSegment(segment_index=i, start_time=a, end_time=b, text="source")
                for i, (a, b) in enumerate([(0, 3), (2, 4), (7, 8)])]
    usable, quality = assess_transcript(segments, duration=10)
    assert len(usable) == 3
    assert quality["coverage_ratio"] == 0.5
    assert {"overlapping_segments", "gapped_transcript", "partial_coverage"} <= set(quality["issues"])
    assert quality["status"] == "partial"


def test_untimed_and_empty_evidence_states():
    segment = TranscriptSegment(segment_index=0, text="Untimed source")
    assert assess_transcript([segment])[1]["status"] == "not_assessable"
    assert assess_transcript([])[1]["status"] == "unavailable"


def test_known_language_mismatch_invalidates_without_losing_source_text():
    segment = TranscriptSegment(segment_index=0, start_time=0, end_time=8, text="Preserve original words")
    usable, quality = assess_transcript([segment], duration=8, source="platform_captions",
        provenance={"original_audio_language": "en", "caption_track_language": "ar"})
    assert usable == []
    assert quality["status"] == "invalid"
    assert quality["raw_segments"][0]["text"] == segment.text


def test_valid_language_metadata_does_not_invent_provider_confidence():
    segment = TranscriptSegment(segment_index=0, start_time=0, end_time=8, text="Source")
    _, quality = assess_transcript([segment], duration=8, source="platform_captions", provenance={
        "original_audio_language": "en", "caption_track_language": "en", "caption_kind": "original"})
    assert quality["status"] == "valid"
    assert "provider_confidence_unavailable" in quality["issues"]
    assert "confidence" not in quality


def test_window_excludes_crossing_words_and_reports_real_range():
    source = [dict(segment_index=0, start_time=0, end_time=54, text="Opening and much later speech")]
    window = select_evidence_window(source)
    assert window.text is None
    assert window.describe()["excluded_boundary_ranges"] == [(0.0, 54.0)]
    assert window.describe()["requested_end"] == 8


def test_narrow_window_overlap_and_untimed_are_not_fabricated():
    source = [dict(start_time=0, end_time=3, text="One"), dict(start_time=2, end_time=4, text="Overlap"),
              dict(start_time=4, end_time=7, text="Beyond five"), dict(text="Untimed")]
    window = select_evidence_window(source, end=5)
    assert window.text == "One"
    assert len(window.boundary_ranges) == 2
    assert window.untimed_count == 1


def test_validation_revision_is_repeatable_and_provenance_sensitive():
    result = VideoExtractionResult(metadata=VideoMetadata(platform="youtube", url="https://youtu.be/synthetic",
        duration_seconds=8, transcript_source="platform_captions", transcript_language="en",
        transcript_evidence={"provenance": {"original_audio_language": "en", "caption_track_language": "en"}}),
        transcript_segments=[TranscriptSegment(segment_index=0, start_time=0, end_time=8, text="source")])
    checked = validate_extraction(result)
    revision = checked.metadata.transcript_evidence["revision"]
    assert validate_extraction(checked).metadata.transcript_evidence["revision"] == revision
    checked.metadata.transcript_evidence["provenance"]["caption_kind"] = "translated"
    assert validate_extraction(checked).metadata.transcript_evidence["revision"] != revision


def test_all_provider_fallbacks_fail_without_fabricated_transcript(monkeypatch):
    from app.services.supadata_transcript_service import SupadataTranscriptUnavailableError
    from app.services.transcription_service import TranscriptionResult
    monkeypatch.setattr(youtube, "get_settings", lambda: SimpleNamespace(youtube_api_key="synthetic-key", supadata_api_key="synthetic-key"))
    monkeypatch.setattr(youtube, "fetch_youtube_info_from_api", lambda *_: {"title": "Synthetic", "duration": 8, "default_audio_language": "en"})
    monkeypatch.setattr(youtube, "fetch_youtube_transcript_with_metadata", lambda *_: TranscriptionResult(segments=[]))
    monkeypatch.setattr(youtube, "transcribe_video_url_with_supadata", lambda *_: (_ for _ in ()).throw(SupadataTranscriptUnavailableError("synthetic failure")))
    monkeypatch.setattr(youtube, "transcribe_youtube_url_with_apify", lambda *_: (_ for _ in ()).throw(AssertionError("Apify must stay suppressed")))
    monkeypatch.setattr(youtube, "_fetch_youtube_audio_info", lambda *_: None)
    result = validate_extraction(youtube.extract_youtube_video("https://youtu.be/synthetic"))
    assert result.transcript_segments == []
    assert result.metadata.transcript_available is False
    assert result.metadata.transcript_evidence["status"] == "unavailable"


def test_hook_analyzer_and_index_use_identical_eight_second_input():
    from app.insights.hook_analyzer import analyze_hook
    from app.rag.chunk_builder import _hook_segments
    source = [dict(segment_index=0, start_time=0, end_time=4, text="First source words"),
              dict(segment_index=1, start_time=6, end_time=8, text="Within eight"),
              dict(segment_index=2, start_time=8, end_time=12, text="Beyond eight")]
    hook = analyze_hook({}, source)
    assert hook.hook_text == "First source words Within eight"
    assert " ".join(s["text"] for s in _hook_segments(source)) == hook.hook_text


def test_caption_is_not_substituted_for_unassessable_verbal_hook():
    from app.insights.hook_analyzer import analyze_hook
    hook = analyze_hook({"description": "A persuasive written caption"}, [])
    assert hook.hook_type == "unavailable"
    assert hook.hook_text is None
