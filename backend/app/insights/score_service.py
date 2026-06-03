import re
from typing import Any

from app.insights.insight_models import HookAnalysis, InsightScores


CTA_TERMS = (
    "follow",
    "comment",
    "share",
    "save",
    "subscribe",
    "watch",
    "learn",
    "try",
    "what do you think",
    "would you",
    "start",
    "ask question",
)
BENEFIT_TERMS = (
    "save",
    "grow",
    "learn",
    "improve",
    "better",
    "faster",
    "easy",
    "benefit",
    "result",
    "so you can",
)
PROBLEM_TERMS = (
    "problem",
    "struggle",
    "pain",
    "hard",
    "stuck",
    "no more",
    "instead",
    "without",
)
SOLUTION_TERMS = (
    "solution",
    "fix",
    "helps",
    "designed",
    "creates",
    "introducing",
    "try",
)
TRANSFORMATION_TERMS = ("before", "after", "from", "to", "transform", "changed")
AUDIENCE_TERMS = (
    "creator",
    "founder",
    "business",
    "brand",
    "student",
    "team",
    "marketer",
    "designer",
    "developer",
    "owner",
    "customer",
    "community",
)


def calculate_metadata_completeness(
    content_item: dict[str, Any],
) -> tuple[int, list[str], list[str]]:
    platform = str(content_item.get("platform") or "")
    field_values = {
        "transcript": bool(content_item.get("transcript_available")),
        "views": content_item.get("views") is not None,
        "likes/reactions": (
            content_item.get("reactions") is not None
            if platform == "facebook"
            else content_item.get("likes") is not None
        ),
        "comments": content_item.get("comments") is not None,
        "creator": _optional_text(content_item.get("creator")) is not None,
        "follower_count/subscriber_count": (
            content_item.get("follower_count") is not None
            or content_item.get("subscriber_count") is not None
        ),
        "hashtags": bool(content_item.get("hashtags")),
        "upload_date": content_item.get("upload_date") is not None,
        "duration_seconds": content_item.get("duration_seconds") is not None,
    }
    available_fields = [
        field_name for field_name, is_available in field_values.items() if is_available
    ]
    missing_fields = [
        field_name
        for field_name, is_available in field_values.items()
        if not is_available
    ]
    score = round((len(available_fields) / len(field_values)) * 10)

    return max(0, min(score, 10)), available_fields, missing_fields


def calculate_engagement_confidence(
    content_item: dict[str, Any],
) -> tuple[int, str]:
    views = _numeric_value(content_item.get("views"))
    interactions = _interaction_count(content_item)
    engagement_rate = _numeric_value(content_item.get("engagement_rate"))

    if views is not None and interactions is not None and engagement_rate is not None:
        return (
            9,
            "High confidence based on confirmed public metrics with views, interactions, and engagement rate available.",
        )

    if views is not None and interactions is not None:
        return (
            7,
            "Medium-high confidence based on confirmed public metrics with views and interactions available.",
        )

    if interactions is not None and views is None:
        return (
            5,
            "Medium-low confidence because confirmed public interactions are available, but views are unavailable.",
        )

    present_metric_count = sum(
        1
        for value in (
            content_item.get("views"),
            content_item.get("likes"),
            content_item.get("reactions"),
            content_item.get("comments"),
            content_item.get("shares"),
        )
        if value is not None
    )

    if present_metric_count >= 2:
        return (
            4,
            "Low-medium confidence because only partial confirmed public metrics are available.",
        )

    if present_metric_count == 1:
        return (
            2,
            "Low confidence because most confirmed public metrics are unavailable.",
        )

    return (
        1,
        "Low confidence because confirmed public engagement metrics are unavailable and must not be estimated.",
    )


def calculate_caption_strength(content_item: dict[str, Any]) -> int:
    text = _content_text(content_item, include_title=True)

    if not text:
        return 0

    normalized = _normalize(text)
    score = 0

    if _has_clear_topic(content_item, normalized):
        score += 2

    if _has_any(normalized, AUDIENCE_TERMS):
        score += 2

    if _has_any(normalized, PROBLEM_TERMS) or _has_any(normalized, BENEFIT_TERMS):
        score += 2

    if _has_any(normalized, CTA_TERMS) or "?" in text:
        score += 2

    if _has_relevant_hashtags(content_item):
        score += 2

    return max(0, min(score, 10))


def calculate_cta_strength(content_item: dict[str, Any]) -> int:
    text = _combined_text(content_item)

    if not text:
        return 0

    normalized = _normalize(text)
    matches = sum(1 for term in CTA_TERMS if term in normalized)

    if "?" in text:
        matches += 1

    if matches <= 0:
        return 0

    return max(0, min(10, 3 + (matches * 2)))


def calculate_audience_specificity(content_item: dict[str, Any]) -> int:
    text = _content_text(content_item, include_title=True)
    hashtags = content_item.get("hashtags")

    if not text and not hashtags:
        return 0

    normalized = _normalize(text)
    score = 0

    if _has_any(normalized, AUDIENCE_TERMS):
        score += 3

    if _has_any(normalized, PROBLEM_TERMS):
        score += 2

    if _has_clear_topic(content_item, normalized):
        score += 2

    if _has_relevant_hashtags(content_item):
        score += 2

    if _has_specific_named_subject(text):
        score += 1

    return max(0, min(score, 10))


def calculate_problem_solution_score(
    content_item: dict[str, Any],
    hook_analysis: HookAnalysis,
) -> int:
    text = " ".join(
        item
        for item in (
            hook_analysis.hook_text,
            _content_text(content_item, include_title=True),
        )
        if item
    )

    if not text:
        return 0

    normalized = _normalize(text)
    score = 0

    if hook_analysis.hook_type == "problem_solution":
        score += 3

    if _has_any(normalized, PROBLEM_TERMS):
        score += 2

    if _has_any(normalized, SOLUTION_TERMS):
        score += 2

    if _has_any(normalized, TRANSFORMATION_TERMS):
        score += 2

    if _has_any(normalized, BENEFIT_TERMS):
        score += 1

    return max(0, min(score, 10))


def calculate_overall_score(scores: InsightScores) -> int:
    weighted_score = (
        scores.hook_clarity * 0.25
        + scores.problem_solution_clarity * 0.20
        + scores.caption_strength * 0.15
        + scores.cta_strength * 0.10
        + scores.audience_specificity * 0.10
        + scores.metadata_completeness * 0.10
        + scores.engagement_confidence * 0.10
    )

    return max(0, min(round(weighted_score), 10))


def _interaction_count(content_item: dict[str, Any]) -> int | None:
    platform = str(content_item.get("platform") or "")

    if platform == "facebook":
        values = (
            _numeric_value(content_item.get("reactions")),
            _numeric_value(content_item.get("comments")),
            _numeric_value(content_item.get("shares")),
        )
    else:
        values = (
            _numeric_value(content_item.get("likes")),
            _numeric_value(content_item.get("comments")),
        )

    available_values = [int(value) for value in values if value is not None]

    if not available_values:
        return None

    return sum(available_values)


def _content_text(content_item: dict[str, Any], include_title: bool = False) -> str:
    parts = [
        _optional_text(content_item.get("caption")),
        _optional_text(content_item.get("description")),
    ]

    if include_title:
        parts.insert(0, _optional_text(content_item.get("title")))

    return " ".join(part for part in parts if part).strip()


def _combined_text(content_item: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _optional_text(content_item.get("title")),
            _optional_text(content_item.get("caption")),
            _optional_text(content_item.get("description")),
        )
        if part
    ).strip()


def _has_clear_topic(content_item: dict[str, Any], normalized_text: str) -> bool:
    if _optional_text(content_item.get("title")) is not None:
        return True

    return bool(re.search(r"\b(product|business|brand|founder|coffee|tool|app|service|creator)\b", normalized_text))


def _has_relevant_hashtags(content_item: dict[str, Any]) -> bool:
    hashtags = content_item.get("hashtags")

    if not isinstance(hashtags, list):
        return False

    clean_tags = [
        str(tag).strip()
        for tag in hashtags
        if isinstance(tag, str) and tag.strip()
    ]

    return len(clean_tags) >= 1


def _has_specific_named_subject(value: str) -> bool:
    return bool(re.search(r"\b[A-Z][a-zA-Z0-9&'-]{2,}\b", value))


def _has_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


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


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())
