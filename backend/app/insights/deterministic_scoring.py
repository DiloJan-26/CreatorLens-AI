"""Deterministic evidence-aware heuristics. No inference, clock or storage side effects."""
from datetime import datetime, UTC
import math
from typing import Any
from app.insights.scoring_models import (
    CreatorMetrics, CreatorScoring, EvidenceAssessment, ScoreBreakdown,
    ScoreComponent, ScoringPolicy,
)


def _count(value: Any) -> int | None:
    # Largest exactly representable integer shared with JavaScript consumers.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > 2**53 - 1 or not math.isfinite(value) or int(value) != value:
        return None
    return int(value)


def _date(value: Any) -> datetime | None:
    try:
        if value is None:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_metrics(item: dict[str, Any]) -> CreatorMetrics:
    platform = str(item.get("platform") or "unknown").lower()
    fields = ("views", "likes", "reactions", "comments", "shares", "subscriber_count", "follower_count")
    counts = {name: _count(item.get(name)) for name in fields}
    primary = "reactions" if platform == "facebook" else "likes"
    required = [primary, "comments"] + (["shares"] if platform == "facebook" else [])
    missing = [name for name in ["views", *required] if counts[name] is None]
    limitations = [f"Invalid {name} rejected." for name in fields if item.get(name) is not None and counts[name] is None]
    views = counts["views"]
    available = [counts[name] for name in required if counts[name] is not None]
    interactions = sum(available) if all(counts[name] is not None for name in required) else None
    rates = {name: (counts[name] / views * 100 if views and counts[name] is not None else None)
             for name in ("likes", "reactions", "comments", "shares")}
    rates["combined_engagement"] = interactions / views * 100 if views and interactions is not None else None
    creator_field = "subscriber_count" if platform == "youtube" else "follower_count"
    size = counts[creator_field]
    inconsistent = bool(views is not None and counts[primary] is not None and counts[primary] > views)
    known_platform = platform in {"youtube", "instagram", "facebook"}
    if inconsistent:
        limitations.append("Likes/reactions exceed views; asynchronous counts or incompatible units prevent rate ranking.")
    status = ("not_assessable" if not known_platform or not views or interactions is None else
              "insufficient_evidence" if views < 1000 or inconsistent else "eligible")
    if status != "eligible":
        limitations.append("Descriptive rates do not establish comparative engagement effectiveness.")
    evidence = item.get("transcript_evidence") or {}
    observed = item.get("observed_at") or item.get("captured_at") or evidence.get("extracted_at")
    published = item.get("upload_date")
    a, b = _date(published), _date(observed)
    age = None
    if a and b:
        # Date-only publication has day resolution; normalize for subtraction only.
        age = ((b.replace(tzinfo=UTC) if b.tzinfo is None else b.astimezone(UTC)) - (a.replace(tzinfo=UTC) if a.tzinfo is None else a.astimezone(UTC))).total_seconds() / 86400
        if age < 0:
            limitations.append("Publication occurs after observation; age unavailable.")
            age = None
    limitations += ["Views are lifetime public counts, not growth velocity.",
        "Current creator size is not historical audience size or subscriber conversion.",
        "Interaction events are not unique users, retention, monetization or causal quality.",
        "Cross-platform interaction definitions and audiences are not equivalent."]
    return CreatorMetrics(platform=platform, counts=counts, rates_percent=rates,
        interaction_definition=required, interactions=interactions,
        available_interactions=sum(available) if available else None, creator_size=size,
        views_per_current_creator_size=views / size if size and views is not None else None,
        interactions_per_current_creator_size=interactions / size if size and interactions is not None else None,
        publication_date=str(published) if published else None, observed_at=str(observed) if observed else None,
        age_days=age, engagement_status=status, missing_inputs=missing, limitations=limitations,
        provenance={"slot": item.get("slot"), "content_item_id": item.get("id"),
                    "source_method": item.get("metric_source_method"), "url": item.get("url")})


def _feature(name: str, raw: float | None, score: float | None, rule: str, source: str) -> ScoreComponent:
    return ScoreComponent(feature=name, raw_value=raw, score=score, rule=rule, source=source)


def _combine(parts: list[ScoreComponent], weights: dict[str, float], *, minimum: int,
             rationale: str, limitations: list[str] | None = None) -> ScoreBreakdown:
    eligible = [p for p in parts if p.score is not None]
    total = sum(weights.values())
    supported = sum(weights[p.feature] for p in eligible)
    assessable = len(eligible) >= minimum
    updated = []
    for p in parts:
        weight = weights[p.feature] / supported if assessable and p.score is not None and supported else 0
        updated.append(p.model_copy(update={"weight": weight,
            "contribution": p.score * weight if weight else None}))
    return ScoreBreakdown(score=round(sum(p.contribution or 0 for p in updated), 3) if assessable else None,
        status=("assessable" if len(eligible) == len(parts) else "partial") if assessable else "not_assessable",
        coverage=supported / total if total else 0, components=updated,
        missing_inputs=[p.feature for p in parts if p.score is None], limitations=limitations or [], rationale=rationale)


def calculate_scoring(item: dict[str, Any], creative_inputs: dict[str, int], *, hook_assessable: bool) -> CreatorScoring:
    metrics = normalize_metrics(item)
    policy = ScoringPolicy()
    views = metrics.counts["views"]
    reach_value = min(10, 10 * math.log1p(views) / math.log1p(10_000_000)) if views is not None else None
    reach = _combine([_feature("reach", views, reach_value, "10*ln(1+views)/ln(1+10000000), capped at 10", "confirmed views")],
        {"reach": 1}, minimum=1, rationale="Uncalibrated lifetime reach heuristic.")
    rate = metrics.rates_percent["combined_engagement"]
    engagement_value = min(10, rate * 2) if rate is not None and metrics.engagement_status == "eligible" else None
    engagement = _combine([_feature("engagement", rate, engagement_value, "min(10,2*combined rate percent); requires all defined interactions and >=1000 views", "+".join(metrics.interaction_definition))],
        {"engagement": 1}, minimum=1, rationale="Event density, not statistical probability or unique-user engagement.", limitations=metrics.limitations)
    performance = _combine([
        _feature("reach", views, reach.score, reach.components[0].rule, "views"),
        _feature("engagement", rate, engagement.score, engagement.components[0].rule, "+".join(metrics.interaction_definition))],
        policy.performance_weights, minimum=2, rationale="Equal reach and engagement weights; partial inputs never lower quality as zero.")
    ratio = metrics.views_per_current_creator_size
    efficiency_value = min(10, 10 * math.log1p(ratio) / math.log1p(50)) if ratio is not None else None
    efficiency = _combine([_feature("audience_normalized_reach", ratio, efficiency_value,
        "10*ln(1+views/current_creator_size)/ln(51), capped at 10", "views and current platform-specific creator size")],
        {"audience_normalized_reach": 1}, minimum=1,
        rationale="Normalized reach only; normalized interactions remain context to avoid another correlated popularity term.",
        limitations=["Zero or missing creator size is not assessable.", "Extreme ratios are not proof of virality.", "Current audience and lifetime views refer to different periods."])
    creative_weights = {"hook_clarity": .30, "problem_solution_clarity": .25, "caption_strength": .20,
                        "cta_strength": .15, "audience_specificity": .10}
    # Preserve legacy formula and rounding, but require usable hook and descriptive text.
    creative_ok = hook_assessable and any(str(item.get(k) or "").strip() for k in ("title", "caption", "description"))
    creative_parts = [_feature(k, creative_inputs[k], creative_inputs[k] if creative_ok else None,
        "Existing deterministic creative rule; weighted .30/.25/.20/.15/.10 then Python round", "validated hook/title/caption/description heuristics") for k in creative_weights]
    creative = _combine(creative_parts, creative_weights, minimum=5, rationale="Legacy creative arithmetic retained; no semantic inference.")
    if creative.score is not None:
        creative.score = round(sum(creative_inputs[k] * w for k, w in creative_weights.items()))
        creative.rationale += " Composite rounded to integer; component contributions are before rounding."
    overall = _combine([
        _feature("public_performance", performance.score, performance.score, "performance composite", "public metrics"),
        _feature("creator_efficiency", efficiency.score, efficiency.score, "normalized reach heuristic", "current audience"),
        _feature("creative_structure", creative.score, creative.score, "existing creative formula", "validated creative evidence")],
        policy.overall_weights, minimum=2, rationale="Eligible weights renormalized; requires performance AND creative. Evidence confidence has no contribution.")
    if performance.score is None or creative.score is None:
        overall.score = None
        overall.status = "not_assessable"
        for p in overall.components:
            p.weight = 0
            p.contribution = None
    evidence = item.get("transcript_evidence") or {}
    required = ["views", *metrics.interaction_definition, "subscriber_count" if metrics.platform == "youtube" else "follower_count"]
    assessment = EvidenceAssessment(metric_completeness=sum(metrics.counts[k] is not None for k in required) / len(required),
        transcript_status=evidence.get("status", "not_assessable"), transcript_revision=evidence.get("revision"),
        source_reliability=str(item.get("metric_source_confidence") or "unverified"), limitations=list(evidence.get("issues") or []) + metrics.limitations)
    signature = [p.feature for p in overall.components if p.score is not None]
    return CreatorScoring(metrics=metrics, reach=reach, engagement=engagement, public_performance=performance,
        creator_efficiency=efficiency, creative_structure=creative, overall=overall, evidence=assessment,
        comparison_signature=[metrics.platform, "+".join(metrics.interaction_definition), *signature])


def comparison_eligibility(left: CreatorScoring, right: CreatorScoring) -> dict:
    compatible = (left.policy.version == right.policy.version and left.comparison_signature == right.comparison_signature
                  and left.overall.score is not None and right.overall.score is not None)
    return {"status": "eligible" if compatible else "insufficient_evidence",
        "reason": "Same policy, platform, interaction definition and eligible dimensions required; no authoritative winner selected.",
        "authoritative_winner": None}
