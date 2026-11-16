"""Build compact sources and validate citations without trusting model assertions."""
import json
import re
from app.models.video import TranscriptSegment
from app.services.evidence_quality import assess_transcript
from app.services.evidence_window import select_evidence_window
from app.services.hash_service import hash_payload
from app.insights.semantic_models import CreativeFeatures, SemanticEvidence, FEATURES

OPENING_FEATURES = {"opening_type", "verbal_hook_clarity", "topic_specificity", "curiosity_gap"}
NARRATIVE_FEATURES = {"audience_benefit", "problem_solution_clarity", "audience_specificity", "spoken_cta"}

def build_semantic_input(project_id: str, item: dict, segments: list[dict], *, supported_languages=("en", "hi", "ta")) -> dict:
    evidence = item.get("transcript_evidence") or {}
    provenance = evidence.get("provenance") or {}
    clean, quality = assess_transcript([TranscriptSegment.model_validate(s) for s in segments],
        duration=item.get("duration_seconds"), provenance=provenance, source=item.get("transcript_source"))
    # Old unknown-language records remain readable but are not silently sent for semantic scoring.
    language = provenance.get("transcript_language") or provenance.get("caption_track_language") or provenance.get("original_audio_language")
    language_supported = bool(language and str(language).lower().split("-")[0] in supported_languages)
    usable = quality["status"] in {"valid", "partial"} and evidence.get("status") in {"valid", "partial"} and bool(evidence.get("revision")) and language_supported and provenance.get("caption_kind") != "translated"
    sources = []
    content_id = str(item.get("id") or item.get("content_item_id") or "")
    def add(kind, text, start=None, end=None):
        if not text.strip():
            return
        payload = dict(project_id=project_id, content_id=content_id, slot=item["slot"], platform=item["platform"],
            source_type=kind, text=text, start_time=start, end_time=end)
        sources.append(SemanticEvidence(id=hash_payload(payload), **payload).model_dump(mode="json"))
    # Bracket-only music/noise captions do not establish verbal evidence.
    clean = [s for s in clean if re.sub(r"\[[^\]]*\]|\([^)]*\)|[\W\d_]", "", s.text).strip()]
    clipped = False
    if usable and content_id:
        window = select_evidence_window([s.model_dump(mode="json") for s in clean])
        if len(window.segments) > 8 or len(clean) > 32:
            clipped = True
        for s in window.segments[:8]:
            if len(s["text"]) <= 2400:
                add("opening", s["text"], s["start_time"], s["end_time"])
        budget = 10000
        for s in clean[:32]:
            if len(s.text) > 2400 or len(s.text) > budget:
                clipped = True
                continue
            add("transcript", s.text, s.start_time, s.end_time)
            budget -= len(s.text)
        description = str(item.get("description") or item.get("caption") or "")
        if len(description) > 2400:
            clipped = True
        add("description", description[:2400])
    complete = usable and evidence.get("status") == "valid" and quality["status"] == "valid" and not clipped
    payload = dict(project_id=project_id, content_id=content_id, slot=item["slot"], platform=item["platform"],
        transcript_revision=evidence.get("revision"), transcript_status=quality["status"], language=language,
        language_provenance=provenance, complete=bool(complete), sources=sources,
        limitations=sorted(set((["semantic_language_unsupported_or_unknown"] if not language_supported else []) + list(evidence.get("issues") or []) + quality["issues"] +
            (["context_budget_truncated"] if clipped else []))))
    payload["input_revision"] = hash_payload(payload)
    return payload


def parse_features(raw: str, context: dict) -> CreativeFeatures:
    # Strict JSON: malformed or unsupported output fails, never becomes synthetic success.
    result = CreativeFeatures.model_validate_json(raw)
    for key in ("project_id", "content_id", "slot", "input_revision"):
        if getattr(result, key) != context[key]:
            raise ValueError("Semantic input identity mismatch.")
    sources = {s["id"]: s for s in context["sources"]}
    for feature in result.features:
        allowed = {"opening"} if feature.feature in OPENING_FEATURES else {"description"} if feature.feature == "description_cta" else {"transcript"} if feature.feature in NARRATIVE_FEATURES else {"opening", "transcript", "description"}
        if feature.value == "absent" and not context["complete"]:
            raise ValueError("Absence cannot be established from incomplete evidence.")
        if feature.feature == "evidence_coverage" and feature.value != "unassessable":
            expected = "clear" if context["complete"] else "partial"
            if feature.value != expected:
                raise ValueError("Coverage must match deterministic input coverage.")
        for ref in feature.evidence:
            source = sources.get(ref.evidence_id)
            if source is None or source["source_type"] not in allowed:
                raise ValueError("Unknown or wrong-type semantic evidence.")
            if ref.content_id != context["content_id"] or ref.slot != context["slot"]:
                raise ValueError("Cross-content citation rejected.")
            if not ref.excerpt.strip() or ref.excerpt not in source["text"]:
                raise ValueError("Excerpt is not an exact source span.")
            if ref.start_time != source["start_time"] or ref.end_time != source["end_time"]:
                raise ValueError("Timestamp must match the actual source segment; word clipping unavailable.")
    return result
