"""Synchronous native captions only: no media download, AI fallback or job polling."""
import json
import math
import time
import httpx
from app.core.config import get_settings
from app.extraction import accounting
from app.extraction.dispatch_limit import enforce_provider_rate
from app.extraction.policy import configuration, input_url, checked_duration, POLICY_VERSION, ExtractionSafetyError
from app.extractors.metadata_normalizer import normalize_metadata
from app.models.video import VideoExtractionResult
from app.services.evidence_quality import validate_extraction
from app.services.supadata_transcript_service import _segments_from_payload

BASE_URL = "https://api.supadata.ai/v1/"


class SafePreSendFailure(ExtractionSafetyError):
    """Local connection-pool exhaustion before any request reached the provider."""


def request(project_id, slot, url, platform, operation):
    settings = get_settings()
    configuration(settings)
    url = input_url(url, platform, settings)
    enforce_provider_rate(settings)
    identifier = accounting.begin_current(project_id, slot, url, platform, operation)
    endpoint = "metadata" if operation == "metadata" else "transcript"
    params = {"url": url}
    if operation == "native_transcript":
        params.update(mode="native", text="false")
        preferred = settings.transcript_language
        if preferred == "multi":
            preferred = next(iter(settings.transcript_fallback_language_list()), None)
        if preferred:
            params["lang"] = preferred
    started = time.monotonic()
    try:
        # No SDK retries, redirects, cookies, remote media fetch or environment proxy.
        with httpx.Client(timeout=httpx.Timeout(settings.extraction_timeout_seconds),
                          transport=httpx.HTTPTransport(retries=0), follow_redirects=False,
                          trust_env=False) as client:
            with client.stream("GET", BASE_URL + endpoint, params=params,
                               headers={"x-api-key": settings.supadata_api_key, "Accept-Encoding": "identity"}) as response:
                if response.status_code in {400, 401, 402, 403, 404, 429}:
                    accounting.finish_current(identifier, "unavailable", response_status=response.status_code, latency_ms=round((time.monotonic()-started)*1000))
                    return None
                if response.status_code not in {200, 206} or response.headers.get("content-encoding", "identity") != "identity":
                    raise ExtractionSafetyError("Unexpected provider response; reconciliation required.")
                chunks, size = [], 0
                for chunk in response.iter_raw():
                    size += len(chunk)
                    if size > settings.extraction_max_response_bytes or time.monotonic() - started > settings.extraction_timeout_seconds:
                        raise ExtractionSafetyError("Provider response exceeded the approved size/time bound.")
                    chunks.append(chunk)
                payload = json.loads(b"".join(chunks))
                if not isinstance(payload, dict) or payload.get("jobId"):
                    raise ExtractionSafetyError("Unexpected or asynchronous provider outcome; no polling or paid replay.")
                duration = None
                if operation == "metadata":
                    if payload.get("platform") != platform or payload.get("type") != "video" or input_url(payload.get("url"), platform, settings) != url:
                        raise ExtractionSafetyError("Provider metadata source identity mismatch.")
                    try:
                        duration = checked_duration((payload.get("media") or {}).get("duration"), settings)
                    except ExtractionSafetyError:
                        accounting.finish_current(identifier, "unavailable", response_status=response.status_code, latency_ms=round((time.monotonic()-started)*1000))
                        raise
                if not accounting.finish_current(identifier, "completed", response_status=response.status_code, verified_duration=duration, latency_ms=round((time.monotonic()-started)*1000)):
                    raise ExtractionSafetyError("Late provider response requires reconciliation before evidence reuse.")
                return payload
    except httpx.PoolTimeout:
        accounting.finish_current(identifier, "safe_failure", latency_ms=round((time.monotonic()-started)*1000))
        raise SafePreSendFailure("Local request pool unavailable before send.") from None
    except BaseException:
        accounting.finish_current(identifier, "needs_reconciliation", latency_ms=round((time.monotonic()-started)*1000))
        raise ExtractionSafetyError("Provider outcome requires reconciliation; no automatic paid retry.") from None


def extract(project_id, slot, platform, url):
    settings = get_settings()
    configuration(settings)
    canonical = input_url(url, platform, settings)
    payload = request(project_id, slot, canonical, platform, "metadata")
    if payload is None:
        raise ExtractionSafetyError("Provider metadata is unavailable; no transcript request was made.")
    if payload.get("platform") != platform or payload.get("type") != "video" or input_url(payload.get("url"), platform, settings) != canonical:
        raise ExtractionSafetyError("Provider metadata identity does not match the requested video.")
    duration = checked_duration((payload.get("media") or {}).get("duration"), settings)
    # One initial transcript attempt + one confirmed pre-send retry, shared by slot.
    try:
        transcript = request(project_id, slot, canonical, platform, "native_transcript")
    except SafePreSendFailure:
        transcript = request(project_id, slot, canonical, platform, "native_transcript")
    transcript = transcript or {}
    segments = _segments_from_payload(transcript)
    stats = payload.get("stats") or {}
    def count(name):
        value = stats.get(name)
        return value if type(value) is int and value >= 0 else None
    author = payload.get("author") or {}
    info = {"title": payload.get("title"), "description": payload.get("description"),
            "uploader": author.get("displayName"), "uploader_id": author.get("username"),
            "view_count": count("views"), "like_count": count("likes"),
            "comment_count": count("comments"), "reaction_count": count("reactions"),
            "share_count": count("shares"), "duration": math.ceil(duration),
            "thumbnail": (payload.get("media") or {}).get("thumbnailUrl"), "tags": payload.get("tags")}
    metadata = normalize_metadata(platform=platform, url=url, slot=slot, info=info,
                                  transcript_available=bool(segments), transcript_segment_count=len(segments),
                                  transcript_language=transcript.get("lang"), transcript_source="supadata_platform_captions" if segments else "unavailable",
                                  extraction_status="ready" if segments else "partial",
                                  metric_source_note="Confirmed Supadata public metadata; missing counts are unavailable.",
                                  transcript_source_note="Native platform captions only; original audio language has not been verified.")
    metadata.transcript_evidence = {"provenance": {"provider": "supadata", "caption_track_language": transcript.get("lang"),
        "requested_languages": [settings.transcript_language] if settings.transcript_language != "multi" else settings.transcript_fallback_language_list()[:1],
        "caption_kind": "translated" if transcript.get("isTranslated") is True else "unknown",
        "audio_language_verified": False, "selection_reason": "bounded_native_preferred_language_with_provider_fallback",
        "extraction_policy": POLICY_VERSION, "source_url_fingerprint": accounting.source_key("source", canonical)}}
    result = validate_extraction(VideoExtractionResult(metadata=metadata, transcript_segments=segments))
    return result


def compatible_cache(result, settings):
    checked_duration(result.metadata.duration_seconds, settings)
    return (result.metadata.transcript_evidence.get("provenance") or {}).get("extraction_policy") == POLICY_VERSION
