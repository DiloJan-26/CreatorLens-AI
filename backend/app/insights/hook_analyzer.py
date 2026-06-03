import re
from typing import Any

from app.insights.insight_models import HookAnalysis


QUESTION_TERMS = ("how", "why", "what", "did you know")
FOUNDER_TERMS = ("founded", "founder", "started", "story")
PROBLEM_TERMS = ("no more", "problem", "struggle", "instead", "solution")
PRODUCT_TERMS = ("designed", "introducing", "creates", "created", "built", "launch")
BENEFIT_TERMS = (
    "save",
    "grow",
    "learn",
    "improve",
    "better",
    "faster",
    "easy",
    "without",
    "so you can",
)
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
    "coffee",
    "shop",
)
TREND_TERMS = ("trend", "viral", "pov", "challenge", "tiktok", "reel")
TRANSFORMATION_TERMS = ("before", "after", "from", "to", "transform", "changed")
WEAK_INTRO_TERMS = ("hi guys", "hello everyone", "welcome back", "today i am")


def analyze_hook(
    content_item: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
) -> HookAnalysis:
    hook_text = _select_hook_text(content_item, transcript_segments)

    if hook_text is None:
        return HookAnalysis(
            hook_text=None,
            hook_type="unavailable",
            hook_score=0,
            clarity_reason="Hook evidence is unavailable from transcript, caption, or description.",
            detected_patterns=[],
        )

    normalized = _normalize(hook_text)
    detected_patterns = _detected_patterns(normalized, hook_text)
    hook_type = _classify_hook(normalized, hook_text, detected_patterns)
    hook_score = _score_hook(normalized, hook_text, detected_patterns)

    return HookAnalysis(
        hook_text=_compact_text(hook_text, 420),
        hook_type=hook_type,
        hook_score=hook_score,
        clarity_reason=_clarity_reason(hook_type, hook_score, detected_patterns),
        detected_patterns=detected_patterns,
    )


def _select_hook_text(
    content_item: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
) -> str | None:
    transcript_text = _hook_from_transcript(transcript_segments)

    if transcript_text:
        return transcript_text

    description = _optional_text(content_item.get("caption")) or _optional_text(
        content_item.get("description")
    )

    if description:
        return _first_sentence(description)

    return None


def _hook_from_transcript(segments: list[dict[str, Any]]) -> str | None:
    clean_segments = [
        segment
        for segment in segments
        if _optional_text(segment.get("text")) is not None
    ]

    if not clean_segments:
        return None

    timed_segments = [
        segment
        for segment in clean_segments
        if (start_time := _as_float(segment.get("start_time"))) is not None
        and start_time <= 8.0
    ]
    selected_segments = timed_segments or clean_segments[:2]
    text = " ".join(
        str(segment.get("text", "")).strip()
        for segment in selected_segments
        if str(segment.get("text", "")).strip()
    ).strip()

    return text or None


def _classify_hook(
    normalized: str,
    original: str,
    patterns: list[str],
) -> str:
    if not normalized:
        return "unavailable"

    if "question" in patterns:
        return "question"

    if "statistic" in patterns and _pattern_count(patterns, "statistic") >= 1:
        return "statistic"

    if _has_any(normalized, FOUNDER_TERMS):
        return "founder_story"

    if _has_any(normalized, PROBLEM_TERMS):
        return "problem_solution"

    if _has_any(normalized, PRODUCT_TERMS):
        return "product_reveal"

    if _has_any(normalized, TRANSFORMATION_TERMS):
        return "transformation"

    if _has_any(normalized, TREND_TERMS):
        return "trend_based"

    if _has_any(normalized, QUESTION_TERMS):
        return "educational" if normalized.startswith(("how", "why", "what")) else "curiosity"

    if _is_weak_intro(normalized, original):
        return "weak_context_only"

    if _has_any(normalized, BENEFIT_TERMS):
        return "educational"

    return "lifestyle"


def _detected_patterns(normalized: str, original: str) -> list[str]:
    patterns: list[str] = []

    if _has_question(original, normalized):
        patterns.append("question")

    if re.search(r"\b\d+(\.\d+)?\b|%|\$|revenue|year", normalized):
        patterns.append("statistic")

    if _has_any(normalized, PROBLEM_TERMS):
        patterns.append("problem_or_solution")

    if _has_any(normalized, FOUNDER_TERMS):
        patterns.append("founder_story")

    if _has_any(normalized, PRODUCT_TERMS):
        patterns.append("product_reveal")

    if _has_any(normalized, BENEFIT_TERMS):
        patterns.append("benefit_or_payoff")

    if _has_any(normalized, AUDIENCE_TERMS):
        patterns.append("audience_relevance")

    if _is_concise(original):
        patterns.append("concise_opening")

    if _has_specific_subject(original):
        patterns.append("specific_subject")

    if _is_weak_intro(normalized, original):
        patterns.append("weak_general_intro")

    return patterns


def _score_hook(normalized: str, original: str, patterns: list[str]) -> int:
    if not normalized:
        return 0

    score = 0

    if "specific_subject" in patterns:
        score += 2

    if "benefit_or_payoff" in patterns or "product_reveal" in patterns:
        score += 2

    if "problem_or_solution" in patterns or "question" in patterns:
        score += 2

    if "concise_opening" in patterns:
        score += 2

    if "audience_relevance" in patterns:
        score += 2

    if "statistic" in patterns and score < 10:
        score += 1

    if "weak_general_intro" in patterns:
        score = min(score, 3)

    return max(0, min(score, 10))


def _clarity_reason(hook_type: str, score: int, patterns: list[str]) -> str:
    if hook_type == "unavailable":
        return "Hook evidence is unavailable."

    if score >= 8:
        return "The hook is clear, specific, and gives viewers an early reason to keep watching."

    if score >= 5:
        return "The hook has usable context, but the payoff or audience relevance could be sharper."

    if "weak_general_intro" in patterns:
        return "The opening is mostly general introduction and does not establish a strong payoff quickly."

    return "The hook needs a clearer subject, tension, benefit, or audience signal."


def _has_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _has_question(original: str, normalized: str) -> bool:
    return "?" in original or normalized.startswith(("how ", "why ", "what ", "would "))


def _is_weak_intro(normalized: str, original: str) -> bool:
    if _has_any(normalized, WEAK_INTRO_TERMS):
        return True

    words = original.split()
    return len(words) < 5 and not re.search(r"\d|[?#]", original)


def _is_concise(value: str) -> bool:
    words = value.split()
    return 5 <= len(words) <= 35


def _has_specific_subject(value: str) -> bool:
    if re.search(r"\b[A-Z][a-zA-Z0-9&'-]{2,}\b", value):
        return True

    return bool(re.search(r"\b(coffee|app|product|brand|business|creator|founder|tool|shop)\b", value.lower()))


def _pattern_count(patterns: list[str], pattern: str) -> int:
    return sum(1 for item in patterns if item == pattern)


def _first_sentence(value: str) -> str:
    match = re.split(r"(?<=[.!?])\s+", value.strip(), maxsplit=1)
    return match[0].strip() if match else value.strip()


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
