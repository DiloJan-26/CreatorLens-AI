from typing import TypedDict

from app.models.chat import QuestionIntent
from app.schemas.retrieval import RetrievalMode


MULTI_SOURCE_INTENTS: frozenset[QuestionIntent] = frozenset(
    {
        "performance_reasoning",
        "hook_analysis",
        "improvement_suggestions",
        "rewrite_request",
        "insight_summary",
        "general",
    }
)


class RetrievalPlan(TypedDict):
    mode: RetrievalMode
    use_structured_metadata: bool
    retrieve: bool
    source_type: str | None
    platform: str | None
    slot: str | None
    top_k: int
    multi_source: bool


def classify_question(message: str) -> QuestionIntent:
    normalized_message = _normalize(message)

    if _contains_any(
        normalized_message,
        ["missing", "unavailable", "metadata", "metadata availability"],
    ):
        return "metadata_missing"
    if _contains_any(
        normalized_message,
        ["score", "insight summary", "creator insight summary", "creator insight score"],
    ):
        return "insight_summary"
    if _contains_any(normalized_message, ["rewrite", "caption", "opening line"]):
        return "rewrite_request"
    if _contains_any(
        normalized_message,
        [
            "hook",
            "first seconds",
            "first 5 seconds",
            "first five seconds",
            "opening",
            "first few seconds",
        ],
    ):
        return "hook_analysis"
    if (
        _contains_any(
            normalized_message,
            [
                "engagement rate",
                "views",
                "likes",
                "comments",
                "metrics",
                "follower count",
            ],
        )
        and not _contains_any(normalized_message, ["why", "explain", "reason"])
    ):
        return "metrics"
    if _contains_any(
        normalized_message,
        [
            "why",
            "outperform",
            "performed better",
            "stronger engagement",
            "more engagement",
            "compare performance",
            "compare",
            "performance",
        ],
    ):
        return "performance_reasoning"
    if _contains_any(
        normalized_message,
        [
            "improve",
            "improvement",
            "suggestions",
            "suggest",
            "recommendation",
            "recommendations",
            "make better",
            "based on",
        ],
    ):
        return "improvement_suggestions"
    if _contains_any(
        normalized_message,
        [
            "facebook",
            "meta",
            "cross-post",
            "cross post",
            "combined engagement",
            "combined meta",
            "verified metrics",
            "metric completeness",
            "follower count",
            "engagement rate",
            "views",
            "likes",
            "comments",
            "metrics",
        ],
    ):
        return "metrics"
    if _contains_any(
        normalized_message,
        ["creator", "followers", "who is", "upload date", "duration", "posted"],
    ):
        return "creator_info"
    if _contains_any(
        normalized_message,
        ["story", "topic", "about", "summarize", "summary"],
    ):
        return "content_summary"
    return "general"


def get_retrieval_plan(intent: QuestionIntent, message: str) -> RetrievalPlan:
    inferred_platform = _infer_platform(message)
    inferred_slot = _infer_slot(message)

    if intent in {"metrics", "creator_info", "metadata_missing"}:
        return _plan(
            mode=RetrievalMode.METRIC_DIRECT,
            retrieve=False,
            source_type=None,
            platform=None,
            top_k=4,
        )
    if intent == "insight_summary":
        return _plan(
            mode=RetrievalMode.STRATEGY_RECOMMENDATION,
            retrieve=True,
            source_type=None,
            platform=None,
            top_k=10,
            multi_source=True,
        )
    if intent == "hook_analysis":
        return _plan(
            mode=RetrievalMode.HOOK_FOCUSED,
            retrieve=True,
            source_type=None,
            platform=None,
            top_k=10,
            multi_source=True,
        )
    if intent == "content_summary":
        return _plan(
            mode=RetrievalMode.TRANSCRIPT_DEEP,
            retrieve=True,
            source_type=None,
            platform=inferred_platform,
            slot=inferred_slot,
            top_k=6,
        )
    if intent == "performance_reasoning":
        return _plan(
            mode=RetrievalMode.BALANCED_COMPARE,
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=12,
            multi_source=True,
        )
    if intent == "improvement_suggestions":
        return _plan(
            mode=RetrievalMode.STRATEGY_RECOMMENDATION,
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=12,
            multi_source=True,
        )
    if intent == "rewrite_request":
        return _plan(
            mode=RetrievalMode.HOOK_FOCUSED,
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=10,
            multi_source=True,
        )
    return _plan(
        mode=RetrievalMode.TRANSCRIPT_DEEP,
        retrieve=True,
        source_type=None,
        platform=inferred_platform,
        slot=inferred_slot,
        top_k=8,
        multi_source=intent in MULTI_SOURCE_INTENTS,
    )


def parse_target_reference_slots(message: str) -> tuple[str | None, str | None]:
    normalized = _normalize(message)
    has_content_1 = "content 1" in normalized or "content one" in normalized
    has_content_2 = "content 2" in normalized or "content two" in normalized
    if not has_content_1 and not has_content_2:
        return None, None

    reference_markers = [
        "from content 1",
        "based on content 1",
        "using content 1",
        "like content 1",
        "from content 2",
        "based on content 2",
        "using content 2",
        "like content 2",
    ]
    for marker in reference_markers:
        if marker not in normalized:
            continue
        if marker.endswith("1"):
            return ("content_2" if has_content_2 else None), "content_1"
        return ("content_1" if has_content_1 else None), "content_2"

    if _contains_any(normalized, ["improve", "rewrite", "fix", "for", "of"]):
        content_1_index = normalized.find("content 1") if has_content_1 else 9999
        content_2_index = normalized.find("content 2") if has_content_2 else 9999
        if content_1_index < content_2_index:
            return "content_1", ("content_2" if has_content_2 else None)
        if content_2_index < content_1_index:
            return "content_2", ("content_1" if has_content_1 else None)
    return None, None


def _plan(
    mode: RetrievalMode,
    retrieve: bool,
    source_type: str | None,
    platform: str | None,
    top_k: int,
    slot: str | None = None,
    multi_source: bool = False,
) -> RetrievalPlan:
    return {
        "mode": mode,
        "use_structured_metadata": True,
        "retrieve": retrieve,
        "source_type": source_type,
        "platform": platform,
        "slot": slot,
        "top_k": top_k,
        "multi_source": multi_source,
    }


def _infer_platform(message: str) -> str | None:
    normalized_message = _normalize(message)
    mentioned_platforms = [
        platform
        for platform in ("youtube", "instagram", "facebook")
        if platform in normalized_message
    ]
    return mentioned_platforms[0] if len(mentioned_platforms) == 1 else None


def _infer_slot(message: str) -> str | None:
    normalized_message = _normalize(message)
    content_1 = "content 1" in normalized_message or "content one" in normalized_message
    content_2 = "content 2" in normalized_message or "content two" in normalized_message
    if content_1 and not content_2:
        return "content_1"
    if content_2 and not content_1:
        return "content_2"
    return None


def _contains_any(message: str, keywords: list[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())
