from typing import TypedDict

from app.models.chat import QuestionIntent

# Intents that require evidence from both content slots.
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
        [
            "missing",
            "unavailable",
            "metadata",
            "metadata availability",
        ],
    ):
        return "metadata_missing"

    if _contains_any(
        normalized_message,
        [
            "score",
            "insight summary",
            "creator insight summary",
            "creator insight score",
        ],
    ):
        return "insight_summary"

    if _contains_any(
        normalized_message,
        [
            "rewrite",
            "caption",
            "opening line",
        ],
    ):
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

    if _contains_any(
        normalized_message,
        [
            "why",
            "outperform",
            "performed better",
            "stronger engagement",
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
        ],
    ):
        return "metrics"

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
            "story",
            "topic",
            "about",
            "summarize",
            "summary",
        ],
    ):
        return "content_summary"

    return "general"


def get_retrieval_plan(intent: QuestionIntent, message: str) -> RetrievalPlan:
    inferred_platform = _infer_platform(message)
    inferred_slot = _infer_slot(message)

    if intent == "metrics":
        return _plan(retrieve=False, source_type=None, platform=None, top_k=4)

    if intent == "creator_info":
        return _plan(retrieve=False, source_type=None, platform=None, top_k=4)

    if intent == "metadata_missing":
        return _plan(retrieve=False, source_type=None, platform=None, top_k=4)

    if intent == "insight_summary":
        return _plan(retrieve=True, source_type=None, platform=None, top_k=10, multi_source=True)

    if intent == "hook_analysis":
        # Retrieve all source types from BOTH slots — balanced retrieval handles hook priority.
        return _plan(retrieve=True, source_type=None, platform=None, top_k=10, multi_source=True)

    if intent == "content_summary":
        return _plan(
            retrieve=True,
            source_type=None,
            platform=inferred_platform,
            slot=inferred_slot,
            top_k=6,
        )

    if intent == "performance_reasoning":
        # Never infer a single slot — reasoning needs both sides.
        return _plan(
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=12,
            multi_source=True,
        )

    if intent == "improvement_suggestions":
        return _plan(
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=12,
            multi_source=True,
        )

    if intent == "rewrite_request":
        # Need hook + description/caption from target AND reference — no source_type filter.
        return _plan(
            retrieve=True,
            source_type=None,
            platform=None,
            slot=None,
            top_k=10,
            multi_source=True,
        )

    return _plan(
        retrieve=True,
        source_type=None,
        platform=inferred_platform,
        slot=inferred_slot,
        top_k=8,
        multi_source=intent in MULTI_SOURCE_INTENTS,
    )


def parse_target_reference_slots(message: str) -> tuple[str | None, str | None]:
    """
    Parse (target_slot, reference_slot) from improvement/rewrite messages.
    E.g. "improve Content 1 from Content 2" → ("content_1", "content_2").
    """
    normalized = _normalize(message)
    has_c1 = "content 1" in normalized or "content one" in normalized
    has_c2 = "content 2" in normalized or "content two" in normalized

    if not has_c1 and not has_c2:
        return None, None

    # "... from/based on/using Content X" → X is the reference.
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
        if marker in normalized:
            if marker.endswith("1"):
                return ("content_2" if has_c2 else None), "content_1"
            else:
                return ("content_1" if has_c1 else None), "content_2"

    # "improve/rewrite/fix Content X" without explicit reference — first mention is target.
    if _contains_any(normalized, ["improve", "rewrite", "fix", "for", "of"]):
        c1_idx = normalized.find("content 1") if has_c1 else 9999
        c2_idx = normalized.find("content 2") if has_c2 else 9999
        if c1_idx < c2_idx:
            return "content_1", ("content_2" if has_c2 else None)
        if c2_idx < c1_idx:
            return "content_2", ("content_1" if has_c1 else None)

    return None, None


def _plan(
    retrieve: bool,
    source_type: str | None,
    platform: str | None,
    top_k: int,
    slot: str | None = None,
    multi_source: bool = False,
) -> RetrievalPlan:
    return {
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
    mentions_youtube = "youtube" in normalized_message
    mentions_instagram = "instagram" in normalized_message
    mentions_facebook = "facebook" in normalized_message

    mentioned_platforms = [
        platform
        for platform, mentioned in (
            ("youtube", mentions_youtube),
            ("instagram", mentions_instagram),
            ("facebook", mentions_facebook),
        )
        if mentioned
    ]

    if len(mentioned_platforms) == 1:
        return mentioned_platforms[0]

    if mentions_youtube and not mentions_instagram and not mentions_facebook:
        return "youtube"

    if mentions_instagram and not mentions_youtube and not mentions_facebook:
        return "instagram"

    return None


def _infer_slot(message: str) -> str | None:
    normalized_message = _normalize(message)
    mentions_content_1 = (
        "content 1" in normalized_message
        or "content one" in normalized_message
    )
    mentions_content_2 = (
        "content 2" in normalized_message
        or "content two" in normalized_message
    )

    if mentions_content_1 and not mentions_content_2:
        return "content_1"

    if mentions_content_2 and not mentions_content_1:
        return "content_2"

    return None


def _contains_any(message: str, keywords: list[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())
