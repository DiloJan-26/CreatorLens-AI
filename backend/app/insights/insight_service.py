from typing import Any

from app.insights.hook_analyzer import analyze_hook
from app.insights.insight_models import (
    ComparisonInsight,
    ContentInsight,
    CreatorInsightSummaryResponse,
    InsightScores,
)
from app.insights.score_service import (
    calculate_audience_specificity,
    calculate_caption_strength,
    calculate_cta_strength,
    calculate_engagement_confidence,
    calculate_metadata_completeness,
    calculate_overall_score,
    calculate_problem_solution_score,
)
from app.services.storage_service import (
    get_project_detail_record,
    get_transcript_segments,
)


class CreatorInsightProjectNotFoundError(Exception):
    """Raised when a Creator Insight Summary is requested for a missing project."""


def get_creator_insight_summary(project_id: str) -> CreatorInsightSummaryResponse:
    project = get_project_detail_record(project_id)

    if project is None:
        raise CreatorInsightProjectNotFoundError("Project not found.")

    content_items = [
        item
        for item in project.get("content_items", [])
        if isinstance(item, dict)
    ]
    content_1 = _content_by_slot(content_items, "content_1")
    content_2 = _content_by_slot(content_items, "content_2")
    content_1_insight = (
        _build_content_insight(project_id, content_1) if content_1 else None
    )
    content_2_insight = (
        _build_content_insight(project_id, content_2) if content_2 else None
    )
    comparison = _build_comparison(
        content_1=content_1,
        content_2=content_2,
        content_1_insight=content_1_insight,
        content_2_insight=content_2_insight,
    )

    return CreatorInsightSummaryResponse(
        project_id=project_id,
        content_1=content_1_insight,
        content_2=content_2_insight,
        comparison=comparison,
        notes=_summary_notes(content_1_insight, content_2_insight),
    )


def _build_content_insight(
    project_id: str,
    content_item: dict[str, Any],
) -> ContentInsight:
    slot = str(content_item.get("slot") or "")
    platform = str(content_item.get("platform") or "")
    transcript_segments = get_transcript_segments(
        project_id=project_id,
        platform=platform,
        slot=slot,
    )
    hook_analysis = analyze_hook(content_item, transcript_segments)
    metadata_score, available_metadata, missing_metadata = (
        calculate_metadata_completeness(content_item)
    )
    engagement_confidence, metric_confidence_note = (
        calculate_engagement_confidence(content_item)
    )
    base_scores = InsightScores(
        hook_clarity=hook_analysis.hook_score,
        problem_solution_clarity=calculate_problem_solution_score(
            content_item,
            hook_analysis,
        ),
        cta_strength=calculate_cta_strength(content_item),
        caption_strength=calculate_caption_strength(content_item),
        audience_specificity=calculate_audience_specificity(content_item),
        metadata_completeness=metadata_score,
        engagement_confidence=engagement_confidence,
        overall_score=0,
    )
    scores = base_scores.model_copy(
        update={"overall_score": calculate_overall_score(base_scores)}
    )
    strengths = _content_strengths(
        content_item=content_item,
        scores=scores,
        hook_type=hook_analysis.hook_type,
    )
    weaknesses = _content_weaknesses(
        scores=scores,
        missing_metadata=missing_metadata,
        hook_type=hook_analysis.hook_type,
    )

    return ContentInsight(
        slot=slot,
        label=_slot_label(slot),
        platform=platform,
        title=_optional_text(content_item.get("title")),
        creator=_optional_text(content_item.get("creator")),
        hook_analysis=hook_analysis,
        scores=scores,
        strengths=strengths,
        weaknesses=weaknesses,
        missing_metadata=missing_metadata,
        available_metadata=available_metadata,
        metric_confidence_note=metric_confidence_note,
        top_improvement=_top_improvement(scores, missing_metadata),
    )


def _build_comparison(
    *,
    content_1: dict[str, Any] | None,
    content_2: dict[str, Any] | None,
    content_1_insight: ContentInsight | None,
    content_2_insight: ContentInsight | None,
) -> ComparisonInsight:
    if content_1 is None or content_2 is None or content_1_insight is None or content_2_insight is None:
        return ComparisonInsight(
            confirmed_metric_winner=None,
            hook_winner=None,
            overall_insight_winner=None,
            main_reason="Creator Insight Summary needs both Content 1 and Content 2 to compare.",
            confidence_note="Comparison is unavailable because one content item is missing.",
            top_recommendations=[
                "Add both supported content URLs before comparing creator insights.",
            ],
            example_rewrite_for_content_2=None,
        )

    metric_winner, metric_reason, metric_confidence = _confirmed_metric_winner(
        content_1,
        content_2,
    )
    hook_winner = _score_winner(
        content_1_insight.scores.hook_clarity,
        content_2_insight.scores.hook_clarity,
        close_threshold=1,
    )
    overall_winner = _score_winner(
        content_1_insight.scores.overall_score,
        content_2_insight.scores.overall_score,
        close_threshold=1,
    )

    return ComparisonInsight(
        confirmed_metric_winner=metric_winner,
        hook_winner=hook_winner,
        overall_insight_winner=overall_winner,
        main_reason=_main_reason(
            metric_reason=metric_reason,
            hook_winner=hook_winner,
            overall_winner=overall_winner,
            content_1_insight=content_1_insight,
            content_2_insight=content_2_insight,
        ),
        confidence_note=_comparison_confidence_note(
            metric_confidence=metric_confidence,
            content_1_insight=content_1_insight,
            content_2_insight=content_2_insight,
        ),
        top_recommendations=_recommendations(
            content_1_insight=content_1_insight,
            content_2_insight=content_2_insight,
        ),
        example_rewrite_for_content_2=_example_rewrite_for_content_2(
            content_1_insight=content_1_insight,
            content_2=content_2,
            content_2_insight=content_2_insight,
        ),
    )


def _confirmed_metric_winner(
    content_1: dict[str, Any],
    content_2: dict[str, Any],
) -> tuple[str | None, str, str]:
    engagement_1 = _numeric_value(content_1.get("engagement_rate"))
    engagement_2 = _numeric_value(content_2.get("engagement_rate"))

    if engagement_1 is not None and engagement_2 is not None:
        return _winner_from_values(
            engagement_1,
            engagement_2,
            "confirmed public engagement rate",
        )

    views_1 = _numeric_value(content_1.get("views"))
    views_2 = _numeric_value(content_2.get("views"))

    if views_1 is not None and views_2 is not None:
        return _winner_from_values(
            views_1,
            views_2,
            "confirmed public views",
        )

    interactions_1 = _interaction_count(content_1)
    interactions_2 = _interaction_count(content_2)

    if interactions_1 is not None and interactions_2 is not None:
        return _winner_from_values(
            float(interactions_1),
            float(interactions_2),
            "confirmed public interactions",
        )

    return (
        None,
        "Confirmed public metric winner is unavailable because comparable key metrics are incomplete.",
        "Metric comparison is limited because one or both content items are missing comparable confirmed public metrics.",
    )


def _winner_from_values(
    content_1_value: float,
    content_2_value: float,
    metric_label: str,
) -> tuple[str | None, str, str]:
    if content_1_value == content_2_value:
        return (
            "Tie",
            f"Content 1 and Content 2 are tied on {metric_label}.",
            f"Winner is based on {metric_label}.",
        )

    winner = "Content 1" if content_1_value > content_2_value else "Content 2"

    return (
        winner,
        f"{winner} leads on {metric_label}.",
        f"Winner is based on {metric_label}.",
    )


def _score_winner(
    content_1_score: int,
    content_2_score: int,
    close_threshold: int,
) -> str:
    difference = abs(content_1_score - content_2_score)

    if difference <= close_threshold:
        return "Tie"

    return "Content 1" if content_1_score > content_2_score else "Content 2"


def _main_reason(
    *,
    metric_reason: str,
    hook_winner: str,
    overall_winner: str,
    content_1_insight: ContentInsight,
    content_2_insight: ContentInsight,
) -> str:
    return (
        f"{metric_reason} Hook Analysis favors {hook_winner}. "
        f"Creator Insight Score favors {overall_winner}. "
        f"Content 1 score: {content_1_insight.scores.overall_score}/10; "
        f"Content 2 score: {content_2_insight.scores.overall_score}/10."
    )


def _comparison_confidence_note(
    *,
    metric_confidence: str,
    content_1_insight: ContentInsight,
    content_2_insight: ContentInsight,
) -> str:
    missing_count = len(content_1_insight.missing_metadata) + len(
        content_2_insight.missing_metadata
    )
    missing_note = (
        f"{missing_count} metadata fields are unavailable across both content items."
        if missing_count
        else "Metadata Availability is complete across the checked fields."
    )

    return (
        f"{metric_confidence} This comparison is based on confirmed public metrics "
        f"and rule-based creator heuristics. {missing_note} Missing metrics are not estimated."
    )


def _recommendations(
    *,
    content_1_insight: ContentInsight,
    content_2_insight: ContentInsight,
) -> list[str]:
    recommendations: list[str] = []
    weaker = (
        content_2_insight
        if content_2_insight.scores.overall_score <= content_1_insight.scores.overall_score
        else content_1_insight
    )
    target_label = weaker.label

    if weaker.scores.hook_clarity < 7:
        recommendations.append(
            f"Make {target_label}'s hook more specific and move the value proposition earlier."
        )

    if weaker.scores.problem_solution_clarity < 7:
        recommendations.append(
            f"Add clearer problem-solution framing to {target_label}."
        )

    if weaker.scores.cta_strength < 6:
        recommendations.append(
            f"Add a simple call to action to {target_label}, such as a comment, save, follow, or learn prompt."
        )

    if weaker.scores.audience_specificity < 6:
        recommendations.append(
            f"Clarify the audience or niche for {target_label} in the opening and caption."
        )

    if weaker.scores.caption_strength < 7:
        recommendations.append(
            f"Improve {target_label}'s caption opening with the topic, benefit, and payoff in the first sentence."
        )

    if "hashtags" in weaker.missing_metadata:
        recommendations.append(
            f"Add platform-relevant hashtags to {target_label} when they fit the content."
        )

    if not recommendations:
        recommendations.append(
            "Keep the strongest hook and caption elements, then test a sharper payoff in the first seconds."
        )

    return recommendations[:5]


def _example_rewrite_for_content_2(
    *,
    content_1_insight: ContentInsight,
    content_2: dict[str, Any],
    content_2_insight: ContentInsight,
) -> str | None:
    topic = _topic_label(content_2)

    if topic is None:
        return None

    if content_1_insight.scores.hook_clarity > content_2_insight.scores.hook_clarity:
        return (
            f"Instead of opening broadly, lead with: \"For {topic}, the first problem is not attention. "
            "It is making the value obvious in the first few seconds.\""
        )

    if content_2_insight.scores.problem_solution_clarity < 7:
        return (
            f"Try: \"If {topic} feels hard to explain, start with the problem, show the change, "
            "then make the payoff clear.\""
        )

    return (
        f"Try: \"Here is the clearest reason {topic} matters, and what viewers should notice first.\""
    )


def _content_strengths(
    *,
    content_item: dict[str, Any],
    scores: InsightScores,
    hook_type: str,
) -> list[str]:
    strengths: list[str] = []

    if scores.hook_clarity >= 7:
        strengths.append(f"Strong Hook Analysis with a {hook_type} opening.")

    if scores.caption_strength >= 7:
        strengths.append("Caption gives useful topic or benefit context.")

    if scores.problem_solution_clarity >= 7:
        strengths.append("Problem-solution framing is clear.")

    if scores.audience_specificity >= 7:
        strengths.append("Audience or niche is specific enough to guide the message.")

    if scores.engagement_confidence >= 7:
        strengths.append("Confirmed Public Metrics are strong enough for engagement confidence.")

    if _numeric_value(content_item.get("engagement_rate")) is not None:
        strengths.append("Engagement rate is available from confirmed public metrics.")

    transcript_language = _language_label(
        content_item.get("detected_language")
        or content_item.get("transcript_language")
    )
    if content_item.get("transcript_available") and transcript_language:
        strengths.append(f"Transcript evidence is available in {transcript_language}.")

    return strengths or ["Some usable creator context is available, but the main strength is not yet clear."]


def _content_weaknesses(
    *,
    scores: InsightScores,
    missing_metadata: list[str],
    hook_type: str,
) -> list[str]:
    weaknesses: list[str] = []

    if scores.hook_clarity < 5 or hook_type in {"weak_context_only", "unavailable"}:
        weaknesses.append("Hook needs a clearer subject, tension, or payoff.")

    if scores.caption_strength < 5:
        weaknesses.append("Caption or description does not strongly explain the topic and benefit.")

    if scores.cta_strength < 5:
        weaknesses.append("Call to action is weak or unavailable.")

    if scores.problem_solution_clarity < 5:
        weaknesses.append("Problem-solution framing is not clear enough.")

    if scores.audience_specificity < 5:
        weaknesses.append("Audience specificity could be stronger.")

    if missing_metadata:
        weaknesses.append(
            "Metadata Availability is incomplete: "
            f"{', '.join(missing_metadata)}."
        )

    return weaknesses or ["No major rule-based weakness detected from available evidence."]


def _top_improvement(
    scores: InsightScores,
    missing_metadata: list[str],
) -> str | None:
    score_map = {
        "hook": scores.hook_clarity,
        "problem_solution": scores.problem_solution_clarity,
        "caption": scores.caption_strength,
        "cta": scores.cta_strength,
        "audience": scores.audience_specificity,
    }
    weakest = min(score_map.items(), key=lambda item: item[1])

    if weakest[1] >= 7 and not missing_metadata:
        return None

    if weakest[0] == "hook":
        return "Move the clearest value proposition into the first seconds."

    if weakest[0] == "problem_solution":
        return "Frame the content around a visible problem, solution, and payoff."

    if weakest[0] == "caption":
        return "Open the caption with the topic and benefit before secondary details."

    if weakest[0] == "cta":
        return "Add one clear next action for viewers."

    return "Name the target audience or niche more directly."


def _summary_notes(
    content_1: ContentInsight | None,
    content_2: ContentInsight | None,
) -> list[str]:
    notes = [
        "Creator Insight Summary uses deterministic heuristics and does not call an LLM.",
        "Missing confirmed public metrics are unavailable and are not estimated.",
    ]
    missing_fields = []

    for insight in (content_1, content_2):
        if insight is None:
            continue
        missing_fields.extend(f"{insight.label}: {field}" for field in insight.missing_metadata)

    if missing_fields:
        notes.append(
            "Metadata Availability limitations: "
            f"{'; '.join(missing_fields[:8])}."
        )

    return notes


def _content_by_slot(
    content_items: list[dict[str, Any]],
    slot: str,
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in content_items
            if str(item.get("slot") or "") == slot
        ),
        None,
    )


def _interaction_count(content_item: dict[str, Any]) -> int | None:
    platform = str(content_item.get("platform") or "")
    values = (
        (
            _numeric_value(content_item.get("reactions")),
            _numeric_value(content_item.get("comments")),
            _numeric_value(content_item.get("shares")),
        )
        if platform == "facebook"
        else (
            _numeric_value(content_item.get("likes")),
            _numeric_value(content_item.get("comments")),
        )
    )
    available_values = [int(value) for value in values if value is not None]

    if not available_values:
        return None

    return sum(available_values)


def _topic_label(content_item: dict[str, Any]) -> str | None:
    for key in ("title", "creator", "creator_handle"):
        text = _optional_text(content_item.get(key))

        if text:
            return _compact_text(text, 80)

    caption = _optional_text(content_item.get("caption")) or _optional_text(
        content_item.get("description")
    )

    if caption:
        return _compact_text(caption, 80)

    platform = _optional_text(content_item.get("platform"))
    return f"{platform} content" if platform else None


def _language_label(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().lower()

    if normalized.startswith("en"):
        return "English"

    if normalized.startswith("hi"):
        return "Hindi"

    if normalized.startswith("ta"):
        return "Tamil"

    if normalized in {"multi", "multilingual"}:
        return "Multilingual"

    return value.strip()


def _slot_label(slot: str) -> str:
    if slot == "content_1":
        return "Content 1"

    if slot == "content_2":
        return "Content 2"

    return "Content"


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
