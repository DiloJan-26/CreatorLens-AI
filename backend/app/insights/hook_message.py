"""Source-bound Hook & Message rules. No provider, embedding, clock or model calls."""
import re
import json
import unicodedata
from copy import deepcopy
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from app.models.video import TranscriptSegment
from app.services.evidence_quality import assess_transcript, language_code
from app.services.evidence_window import select_evidence_window
from app.services.hash_service import hash_payload

POLICY = "hook-message-2.0.0"
WORDS = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.I)
ANNOTATIONS = re.compile(r"\[[^\]]*\]|\((?:music|applause|laughter|silence|inaudible|sound effects?)(?: playing)?\)", re.I)
STOP = frozenset("a an the of in on to for and or with is are was were how why what when where which your you this that it its video explained explanation minute minutes role introduction official episode part shorts short".split())
INTRO = re.compile(r"^(?:\[[^\]]*\]\s*)*(?P<phrase>hi (?:guys|everyone)|hello(?: everyone| guys)?|welcome (?:back|to)|today i am)\b", re.I)
TAKEAWAY = re.compile(r"\b(?:you(?:'ll| will) learn|by the end(?: of (?:this|the) (?:video|lesson|tutorial))?,?\s+you(?:'ll| will| can)\s+(?:learn|understand|know)|you can learn|learn how to|this video (?:explains|shows|covers|will show)|i(?:'ll| will) (?:show|explain)|we(?:'ll| will) (?:show|explain|cover))\b", re.I)
LIMITATION = "Text matches describe the inspected wording; they do not measure creativity, retention or performance effects."


class HookScope(BaseModel):
    kind: Literal["timed", "word_passage", "description", "unavailable"] = "unavailable"
    label: str = "Opening evidence unavailable"
    coverage: Literal["complete", "partial", "word_limited", "unavailable"] = "unavailable"
    requested_end: float | None = None
    actual_ranges: list[tuple[float, float]] = Field(default_factory=list)
    word_count: int = 0


class HookAssessment(BaseModel):
    id: str
    rule_id: str
    policy_version: str = POLICY
    status: Literal["detected", "not_detected", "not_assessable"]
    matched: bool | None
    title: str
    observation: str
    measured: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_quality: Literal["complete", "local", "unavailable"]
    scope: HookScope
    excerpt: str | None = None
    excerpt_start: int | None = None
    excerpt_end: int | None = None
    action_eligible: bool = False
    limitation: str = LIMITATION


class HookMessageAnalysis(BaseModel):
    policy_version: str = POLICY
    status: Literal["assessed", "partial", "not_assessable"]
    topic_candidates: list[str]
    opening_scope: HookScope
    assessments: list[HookAssessment]
    limitations: list[str]


def normalize(value):
    return unicodedata.normalize("NFKC", str(value or "")).replace("\u2019", "'").casefold()


def spoken_text(value):
    return normalize(ANNOTATIONS.sub(" ", value))


def topic_terms(title):
    # Literal title-derived candidates, never inferred semantic subjects or series labels.
    return sorted({m.group() for m in WORDS.finditer(normalize(title)[:500])
                   if len(m.group()) > 2 and not m.group().isdigit() and m.group() not in STOP})


def _speech(segment):
    text = ANNOTATIONS.sub(" ", segment.text)
    return bool(re.search(r"[a-zA-Z\u0080-\uffff]", text))


def _quote(text, start=0, limit=200):
    left = max(0, start - 45) if start > limit else 0
    right = min(len(text), left + limit)
    return text[left:right], left, right


def analyze_hook_message(project_id, item, raw, segments):
    # Small process-local cache, bounded to 64 evidence snapshots. Identity, policy
    # and every analysis input are included; caller mutation cannot poison a hit.
    fields = ("title", "description", "caption", "transcript_language", "description_language",
              "duration_seconds", "transcript_source", "transcript_evidence")
    payload = dict(policy=POLICY, project_id=project_id,
        item={k:item[k] for k in ("content_id", "slot", "platform", "input_revision")},
        raw={k:raw.get(k) for k in fields}, segments=segments)
    return deepcopy(_cached_analysis(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)))


@lru_cache(maxsize=64)
def _cached_analysis(payload_json):
    payload = json.loads(payload_json)
    return _analyze_hook_message(payload["project_id"], payload["item"], payload["raw"], payload["segments"])


def _analyze_hook_message(project_id, item, raw, segments):
    evidence = raw.get("transcript_evidence") or {}
    provenance = evidence.get("provenance") or {}
    candidates = topic_terms(raw.get("title"))
    language = language_code(provenance.get("detected_text_language") or provenance.get("transcript_language")
        or provenance.get("caption_track_language") or raw.get("transcript_language"))
    english = bool(language and language.split("-")[0] == "en")
    refs, findings, limitations = [], [], []
    opening = HookScope()
    text = ""
    opening_ref = None
    selected_segments = []
    reason = "No current opening transcript is available."
    quality = None
    try:
        supplied = [TranscriptSegment.model_validate(s) for s in segments]
        original = [TranscriptSegment.model_validate(s) for s in evidence.get("raw_segments", [])] or supplied
        clean, quality = assess_transcript(original, duration=raw.get("duration_seconds"), provenance=provenance,
            source=raw.get("transcript_source") or evidence.get("provider"), confidence=evidence.get("provider_confidence"))
        current = bool(evidence.get("revision") and quality["revision"] == evidence["revision"]
            and quality["status"] == evidence.get("status") and [s.model_dump() for s in clean] == [s.model_dump() for s in supplied])
        if supplied and not current:
            reason = "The transcript revision does not match the available evidence."
            limitations.append(reason)
        elif quality["status"] == "invalid" or evidence.get("status") == "invalid":
            reason = "Invalid transcript evidence was excluded."
        elif not english:
            reason = "Opening checks require declared English transcript evidence."
        elif current and clean:
            speech = [s for s in clean if _speech(s)]
            if not speech:
                reason = "No spoken opening passage is available; music or sound labels are not speech."
            else:
                window = select_evidence_window([s.model_dump() for s in speech])
                if window.text and len(window.text) <= 2400:
                    text = window.text
                    selected_segments = window.segments
                    ranges = [(s["start_time"], s["end_time"]) for s in selected_segments]
                    duration = raw.get("duration_seconds")
                    target = min(8.0, duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0 else 8.0
                    complete = ranges[0][0] <= 1e-6 and ranges[-1][1] >= target - 1e-6 and not window.boundary_ranges and not window.untimed_count
                    complete = complete and all(b[0] <= a[1] + 1e-6 for a, b in zip(ranges, ranges[1:]))
                    scope_text = f"Inspected speech {ranges[0][0]:g}-{ranges[-1][1]:g}s"
                    if len(ranges) > 1 and any(b[0] > a[1] + 1e-6 for a, b in zip(ranges, ranges[1:])):
                        scope_text += " (with gaps)"
                    opening = HookScope(kind="timed", label=scope_text, coverage="complete" if complete else "partial",
                        requested_end=target, actual_ranges=ranges, word_count=len(WORDS.findall(text)))
                elif speech[0].start_time is None or speech[0].start_time <= 1e-6:
                    passage = " ".join(s.text for s in speech)
                    # Exact prefix of the source text; no fabricated word-level timing.
                    words = list(re.finditer(r"\S+", passage))
                    text = passage[:words[min(40, len(words)) - 1].end()]
                    opening = HookScope(kind="word_passage", label="First 40-word passage of available speech", coverage="word_limited",
                        word_count=min(40, len(words)))
                    limitations.append("This word-limited passage cannot establish an eight-second opening or exact word timings.")
                else:
                    reason = "The available speech does not establish the start of the video."
    except (ValidationError, TypeError, ValueError):
        reason = "Transcript validation failed; opening checks were omitted."
        limitations.append(reason)

    def reference(kind, content, revision, scope):
        # Only continuous timed speech receives an aggregate range; gaps retain separate ranges.
        start = end = None
        if scope.kind == "timed" and scope.actual_ranges and all(b[0] <= a[1] + 1e-6 for a,b in zip(scope.actual_ranges,scope.actual_ranges[1:])):
            start, end = scope.actual_ranges[0][0], scope.actual_ranges[-1][1]
        payload = dict(project_id=project_id, content_id=item["content_id"], slot=item["slot"], platform=item["platform"],
            source_type=kind, text=content, evidence_revision=revision, start_time=start, end_time=end)
        ref = dict(evidence_id=hash_payload(payload), **payload)
        refs.append(ref)
        return ref

    def add(rule, title, status, observation, scope, ref=None, measured=None, action=False, quote_start=0):
        if ref and not quote_start and measured:
            anchor = measured.get("matched_phrase") or next(iter(measured.get("matching_terms") or []), None)
            match = re.search(re.escape(anchor), ref["text"], re.I) if anchor else None
            if match: quote_start = match.start()
        quote, left, right = _quote(ref["text"], quote_start) if ref else (None, None, None)
        finding = HookAssessment(id=hash_payload([POLICY, item["content_id"], rule, ref["evidence_id"] if ref else item["input_revision"]]),
            rule_id=rule, title=title, status=status, matched=True if status == "detected" else False if status == "not_detected" else None,
            observation=observation, scope=scope, evidence_ids=[ref["evidence_id"]] if ref else [], measured=measured or {},
            evidence_quality="complete" if ref and scope.coverage == "complete" else "local" if ref else "unavailable",
            excerpt=quote, excerpt_start=left, excerpt_end=right, action_eligible=action)
        findings.append(finding)

    if text:
        opening_ref = reference("opening" if opening.kind == "timed" else "transcript", text, evidence["revision"], opening)
        tokens = list(WORDS.finditer(spoken_text(text)))
        matches = sorted(set(candidates).intersection(m.group() for m in tokens))
        first = next(((i + 1, m) for i, m in enumerate(tokens) if m.group() in candidates), None)
        measured = dict(topic_candidates=candidates, matching_terms=matches, matched_count=len(matches), eligible_count=len(candidates),
            topic_coverage=len(matches) / len(candidates) if candidates else None, scope=opening.label)
        enough = opening.coverage == "complete"
        topic_status = "detected" if matches else "not_detected" if candidates and enough else "not_assessable"
        topic_text = f"Title terms found: {', '.join(matches)} ({len(matches)} of {len(candidates)})." if matches else (
            "No title-derived topic terms matched in the inspected opening." if topic_status == "not_detected" else
            "No eligible title terms are available for this check." if not candidates else "The partial passage cannot establish whether title terms appear throughout the opening window.")
        add("opening_topic", "Topic introduction", topic_status, topic_text, opening, opening_ref, measured,
            action=topic_status == "not_detected")
        if first:
            position, word = first
            match_range = None
            offset = 0
            for segment in selected_segments:
                count = len(WORDS.findall(spoken_text(segment["text"])))
                if offset < position <= offset + count:
                    match_range = [segment["start_time"], segment["end_time"]]
                    break
                offset += count
            add("topic_position", "Topic placement", "detected", f"The first title-term match is at word {position} of the inspected passage.",
                opening, opening_ref, dict(first_term=word.group(), word_position=position, segment_range=match_range,
                    timing_precision="segment_range" if match_range else "word_position_only", scope=opening.label))
        else:
            add("topic_position", "Topic placement", "not_assessable", "No matched title term is available to locate.", opening)
        introduction = INTRO.search(spoken_text(text))
        precedes = bool(introduction and first and introduction.end() <= first[1].start())
        intro_status = "detected" if introduction else "not_detected" if enough else "not_assessable"
        intro_text = ("A welcome-style introduction" if introduction and introduction.group("phrase").startswith("welcome") else "A greeting or introduction")
        intro_text += " appears before the first matched title term." if precedes else " starts the inspected passage."
        if not introduction:
            intro_text = "No recognized greeting starts the inspected opening." if enough else "Introduction style cannot be assessed across the full opening window."
        add("generic_intro", "Introduction pattern", intro_status, intro_text, opening, opening_ref,
            dict(matched_phrase=introduction.group("phrase") if introduction else None, precedes_topic=precedes if first else None, scope=opening.label),
            action=bool(introduction))
        takeaway = TAKEAWAY.search(spoken_text(text))
        takeaway_status = "detected" if takeaway else "not_detected" if enough else "not_assessable"
        takeaway_text = "An explicit learning or explanation phrase is present." if takeaway else (
            "No recognized learning-promise phrase appears in the inspected opening." if enough else
            "The partial passage cannot establish whether an explicit takeaway appears throughout the opening window.")
        add("explicit_takeaway", "Viewer takeaway", takeaway_status, takeaway_text, opening, opening_ref,
            dict(matched_phrase=takeaway.group() if takeaway else None, scope=opening.label), action=takeaway_status == "not_detected")
    else:
        for rule, title in (("opening_topic", "Topic introduction"), ("topic_position", "Topic placement"),
                            ("generic_intro", "Introduction pattern"), ("explicit_takeaway", "Viewer takeaway")):
            add(rule, title, "not_assessable", reason, opening)

    description = str(raw.get("description") or raw.get("caption") or "").strip()
    if description and candidates:
        prefix = description[:600]
        if len(description) > 600 and not description[600].isspace() and " " in prefix:
            prefix = prefix.rsplit(" ", 1)[0]
        scope = HookScope(kind="description", label=f"First {len(prefix)} description characters", coverage="complete")
        desc_ref = reference("description", prefix, item["input_revision"], scope)
        matches = sorted(set(candidates).intersection(WORDS.findall(normalize(prefix))))
        # Literal title-term overlap is observable without guessing description language.
        # Absence-based wording advice requires independently declared English description text.
        desc_language = language_code(raw.get("description_language") or provenance.get("description_language"))
        action = not matches and bool(desc_language and desc_language.split("-")[0] == "en")
        add("description_topic", "Description alignment", "detected" if matches else "not_detected",
            f"Description names title terms: {', '.join(matches)} ({len(matches)} of {len(candidates)})." if matches else
            "No title-derived terms matched in the inspected description text.", scope, desc_ref,
            dict(topic_candidates=candidates, matching_terms=matches, topic_coverage=len(matches) / len(candidates),
                description_language=desc_language, scope=scope.label), action=action)
    else:
        add("description_topic", "Description alignment", "not_assessable", "A description and eligible title terms are needed for this check.", HookScope())
    if provenance.get("caption_kind") == "translated":
        limitations.append("Opening findings describe translated captions, not verified original spoken wording.")
        for finding in findings:
            if finding.scope.kind in {"timed", "word_passage"}:
                finding.action_eligible = False
    if opening.coverage == "partial":
        limitations.append("Partial or gapped speech does not establish absence throughout the full opening window.")
    assessed = [f for f in findings if f.status != "not_assessable"]
    status = "assessed" if len(assessed) == len(findings) and opening.coverage == "complete" else "partial" if assessed else "not_assessable"
    analysis = HookMessageAnalysis(status=status, topic_candidates=candidates, opening_scope=opening, assessments=findings,
        limitations=list(dict.fromkeys(limitations)))
    return analysis.model_dump(mode="json"), refs
