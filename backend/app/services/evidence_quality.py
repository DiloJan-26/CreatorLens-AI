"""Deterministic evidence integrity policy; no model or provider calls."""
from datetime import UTC, datetime
import math
from typing import Any

from app.models.video import TranscriptSegment, VideoExtractionResult
from app.services.hash_service import hash_payload

EVIDENCE_POLICY_VERSION = "transcript-integrity-1"


def language_code(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower().replace("_", "-")


def language_matches(left: Any, right: Any) -> bool:
    a, b = language_code(left), language_code(right)
    return bool(a and b and a.split("-")[0] == b.split("-")[0])


def finite_time(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) else None


def _raw_segment(segment: TranscriptSegment) -> dict[str, Any]:
    result = segment.model_dump(mode="json")
    for key in ("start_time", "end_time"):
        if isinstance(result[key], float) and not math.isfinite(result[key]):
            result[key] = str(result[key])
    return result


def assess_transcript(segments: list[TranscriptSegment], *, duration: float | None = None,
                      provenance: dict[str, Any] | None = None, source: str | None = None,
                      confidence: float | None = None) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    provenance = dict(provenance or {})
    issues: list[str] = []
    usable: list[TranscriptSegment] = []
    rejected: list[dict[str, Any]] = []
    ranges: list[tuple[float, float]] = []
    duration = finite_time(duration)
    if duration is not None and duration <= 0:
        duration = None
    if duration is None:
        issues.append("video_duration_unknown")
    audio = language_code(provenance.get("original_audio_language"))
    track = language_code(provenance.get("caption_track_language"))
    text_language = language_code(provenance.get("detected_text_language"))
    declared = language_code(provenance.get("transcript_language"))
    mismatch = bool(audio and any(not language_matches(audio, value)
        for value in (track, text_language, declared) if value))
    if track and text_language and not language_matches(track, text_language):
        mismatch = True
        issues.append("track_text_language_mismatch")
    if mismatch:
        issues.append("source_language_mismatch")
    if not audio:
        issues.append("audio_language_unknown")
    if not track and not text_language and not declared:
        issues.append("transcript_language_unknown")
    if provenance.get("caption_kind", "unknown") == "unknown":
        issues.append("caption_origin_unknown")
    if provenance.get("caption_kind") == "translated":
        issues.append("translated_caption")
    if confidence is None:
        issues.append("provider_confidence_unavailable")
    elif isinstance(confidence, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        issues.append("provider_confidence_invalid")
    if not source or source == "unavailable":
        issues.append("provider_provenance_unknown")
    for segment in segments:
        start, end = finite_time(segment.start_time), finite_time(segment.end_time)
        invalid = not segment.text.strip()
        if invalid:
            issues.append("empty_text")
        if segment.start_time is None and segment.end_time is None:
            issues.append("untimed_segments")
        elif start is None or end is None:
            issues.append("invalid_or_incomplete_timestamp")
            invalid = True
        elif start < 0 or end <= start:
            issues.append("negative_or_reversed_timestamp")
            invalid = True
        elif duration is not None and end > duration + 0.25:
            issues.append("beyond_video_duration")
            invalid = True
        if invalid or mismatch:
            rejected.append(_raw_segment(segment))
            continue
        usable.append(segment)
        if start is not None and end is not None:
            ranges.append((start, end))
    if ranges != sorted(ranges):
        issues.append("out_of_order_segments")
    intervals = sorted(ranges)
    covered = 0.0
    previous_end = 0.0
    for start, end in intervals:
        if start < previous_end:
            issues.append("overlapping_segments")
        if start - previous_end > 1.5:
            issues.append("gapped_transcript")
        covered += max(0.0, end - max(start, previous_end))
        previous_end = max(previous_end, end)
    coverage = min(covered / duration, 1.0) if duration and intervals else None
    if coverage is not None and coverage < 0.92:
        issues.append("partial_coverage")
    if duration and intervals and duration - previous_end > 1.5:
        issues.append("trailing_gap")
    if not segments:
        status = "unavailable"
    elif not usable:
        status = "invalid"
    elif not ranges:
        status = "not_assessable"
    else:
        limitations = set(issues) - {"provider_confidence_unavailable"}
        status = "partial" if limitations else "valid"
    identity = {"policy_version": EVIDENCE_POLICY_VERSION, "provenance": provenance,
                "source": source, "segments": [_raw_segment(s) for s in segments],
                "duration": duration, "status": status}
    return usable, {"policy_version": EVIDENCE_POLICY_VERSION, "status": status,
        "issues": sorted(set(issues)), "provenance": provenance, "coverage_ratio": coverage,
        "revision": hash_payload(identity), "provider": source, "provider_confidence": confidence if confidence is not None and not isinstance(confidence, bool) and math.isfinite(confidence) and 0 <= confidence <= 1 else None,
        "rejected_segments": rejected,
        "validated_at": datetime.now(UTC).isoformat(), "raw_segments": [_raw_segment(s) for s in segments],
        "raw_cache_reused": False,
        "validated_cache_reused": False}


def validate_extraction(result: VideoExtractionResult) -> VideoExtractionResult:
    metadata = result.metadata
    existing = metadata.transcript_evidence or {}
    provenance = dict(existing.get("provenance") or {})
    provenance.setdefault("caption_kind", "unknown")
    provenance.setdefault("requested_languages", [])
    provenance.setdefault("detected_text_language", None)
    provenance.setdefault("transcript_language", metadata.transcript_language)
    # Caption labels are not detected transcript-text language or audio verification.
    if metadata.transcript_source == "deepgram_multilingual":
        provenance.setdefault("original_audio_language", metadata.detected_language)
        provenance.setdefault("audio_language_source", "deepgram_audio_analysis")
        provenance.setdefault("audio_language_verified", bool(metadata.detected_language))
    else:
        provenance.setdefault("caption_track_language", metadata.transcript_language)
        provenance.setdefault("audio_language_verified", False)
    raw_segments = [TranscriptSegment.model_validate(s) for s in existing.get("raw_segments", [])] or result.transcript_segments
    usable, evidence = assess_transcript(raw_segments,
        duration=metadata.duration_seconds, provenance=provenance,
        source=metadata.transcript_source, confidence=metadata.language_confidence)
    evidence["extracted_at"] = existing.get("extracted_at", datetime.now(UTC).isoformat())
    if existing.get("cache_age_unknown"):
        evidence["cache_age_unknown"] = True
        evidence["issues"] = sorted(set(evidence["issues"] + ["cache_age_unknown"]))
        if evidence["status"] == "valid":
            evidence["status"] = "partial"
    metadata.transcript_evidence = evidence
    metadata.transcript_available = bool(usable)
    metadata.transcript_segment_count = len(usable)
    if evidence["status"] != "valid" and metadata.extraction_status == "ready":
        metadata.extraction_status = "partial"
    if not usable and "transcript" not in metadata.missing_fields:
        metadata.missing_fields.append("transcript")
    result.transcript_segments = usable
    return result
