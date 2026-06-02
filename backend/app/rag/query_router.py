from typing import TypedDict

from app.models.chat import QuestionIntent


class RetrievalPlan(TypedDict):
    use_structured_metadata: bool
    retrieve: bool
    source_type: str | None
    platform: str | None
    top_k: int


def classify_question(message: str) -> QuestionIntent:
    normalized_message = _normalize(message)

    if _contains_any(
        normalized_message,
        [
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
        [
            "creator",
            "follower count",
            "followers",
            "who is",
            "upload date",
            "duration",
            "posted",
        ],
    ):
        return "creator_info"

    if _contains_any(
        normalized_message,
        [
            "hook",
            "first 5 seconds",
            "first five seconds",
            "opening",
            "first few seconds",
        ],
    ):
        return "hook_comparison"

    if _contains_any(
        normalized_message,
        [
            "story",
            "topic",
            "about",
            "summarize",
            "summary",
        ],
    ):
        return "content_summary"

    if _contains_any(
        normalized_message,
        [
            "why",
            "outperform",
            "performed better",
            "more engagement",
            "compare performance",
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
            "rewrite",
            "make better",
            "based on",
        ],
    ):
        return "improvement_suggestions"

    return "general"


def get_retrieval_plan(intent: QuestionIntent, message: str) -> RetrievalPlan:
    inferred_platform = _infer_platform(message)

    if intent == "metrics":
        return _plan(retrieve=False, source_type=None, platform=None, top_k=4)

    if intent == "creator_info":
        return _plan(retrieve=False, source_type=None, platform=None, top_k=4)

    if intent == "hook_comparison":
        return _plan(retrieve=True, source_type="hook", platform=None, top_k=4)

    if intent == "content_summary":
        return _plan(
            retrieve=True,
            source_type=None,
            platform=inferred_platform,
            top_k=6,
        )

    if intent == "performance_reasoning":
        return _plan(retrieve=True, source_type=None, platform=None, top_k=8)

    if intent == "improvement_suggestions":
        return _plan(retrieve=True, source_type=None, platform=None, top_k=8)

    return _plan(
        retrieve=True,
        source_type=None,
        platform=inferred_platform,
        top_k=6,
    )


def _plan(
    retrieve: bool,
    source_type: str | None,
    platform: str | None,
    top_k: int,
) -> RetrievalPlan:
    return {
        "use_structured_metadata": True,
        "retrieve": retrieve,
        "source_type": source_type,
        "platform": platform,
        "top_k": top_k,
    }


def _infer_platform(message: str) -> str | None:
    normalized_message = _normalize(message)
    mentions_youtube = "youtube" in normalized_message
    mentions_instagram = "instagram" in normalized_message

    if mentions_youtube and not mentions_instagram:
        return "youtube"

    if mentions_instagram and not mentions_youtube:
        return "instagram"

    return None


def _contains_any(message: str, keywords: list[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())
