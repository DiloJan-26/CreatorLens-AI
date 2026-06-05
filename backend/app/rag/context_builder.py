from typing import Any

from app.insights.insight_models import (
    ComparisonInsight,
    ContentInsight,
    CreatorInsightSummaryResponse,
)
from app.insights.insight_service import get_creator_insight_summary
from app.models.chat import ChatMessage, Citation, RagContext
from app.models.metrics import MetricSourceRecord, MetricSummaryResponse
from app.models.rag import RetrieveRequest, RetrievedChunk
from app.rag.query_router import (
    MULTI_SOURCE_INTENTS,
    classify_question,
    get_retrieval_plan,
    parse_target_reference_slots,
)
from app.rag.retrieval_service import retrieve_balanced_evidence, retrieve_project_chunks
from app.services.metric_source_service import get_metric_summary
from app.services.storage_service import get_project_detail_record


class RagContextProjectNotFoundError(Exception):
    """Raised when RAG context is requested for a missing project."""


class RagContextValidationError(Exception):
    """Raised when RAG context input is invalid."""


def build_structured_metadata_context(project_id: str) -> str:
    project = get_project_detail_record(project_id)

    if project is None:
        raise RagContextProjectNotFoundError("Project not found.")

    content_items = [
        item
        for item in project.get("content_items", [])
        if isinstance(item, dict)
    ]
    sections = [
        _platform_metadata_section(_content_label(item), item)
        for item in content_items
    ]
    sections.append(build_metric_source_context(project_id))
    insight_context = build_creator_insight_context(project_id)

    if insight_context:
        sections.append(insight_context)

    return "\n\n".join(sections)


def build_creator_insight_context(project_id: str) -> str:
    try:
        summary = get_creator_insight_summary(project_id)
    except Exception:
        return ""

    lines = ["Creator Insight Summary:"]

    if summary.content_1 is not None:
        lines.extend(_content_insight_lines(summary.content_1))

    if summary.content_2 is not None:
        lines.extend(_content_insight_lines(summary.content_2))

    lines.extend(_comparison_insight_lines(summary.comparison))

    for note in summary.notes:
        lines.append(f"- Missing metadata note: {note}")

    return "\n".join(lines)


def build_metric_source_context(project_id: str) -> str:
    summary = get_metric_summary(project_id)
    lines = ["Metric Source Resolver Summary:"]

    if summary.records:
        for record in summary.records:
            lines.append(
                f"- {_platform_label(record.source_platform)} {record.metric_scope}: "
                f"{_metric_record_summary(record)}"
            )
    else:
        lines.append("- No extracted metric source records are available yet.")

    if summary.combined_meta_engagement_rate is not None:
        lines.append(
            "- Combined Meta engagement: "
            f"views {_display_number(summary.combined_meta_views)}; "
            f"interactions {_display_number(summary.combined_meta_interactions)}; "
            f"engagement rate {_display_percent(summary.combined_meta_engagement_rate)}."
        )
    else:
        lines.append(
            "- Combined Meta engagement: unavailable unless required public or "
            "verified Meta values are available."
        )

    for note in summary.notes:
        lines.append(f"- Note: {note}")

    lines.append("- Rule: unavailable confirmed public metrics must not be estimated.")

    return "\n".join(lines)


def build_rag_context(
    project_id: str,
    message: str,
    recent_messages: list[ChatMessage] | None = None,
) -> RagContext:
    query = message.strip()

    if not query:
        raise RagContextValidationError("Message must not be empty.")

    project = get_project_detail_record(project_id)

    if project is None:
        raise RagContextProjectNotFoundError("Project not found.")

    intent = classify_question(query)
    plan = get_retrieval_plan(intent=intent, message=query)
    structured_context = build_structured_metadata_context(project_id)
    retrieved_context = ""
    citations: list[Citation] = []

    if plan["retrieve"]:
        if plan.get("multi_source") or intent in MULTI_SOURCE_INTENTS:
            target_slot, reference_slot = parse_target_reference_slots(query)
            retrieval_response = retrieve_balanced_evidence(
                project_id=project_id,
                message=query,
                target_slot=target_slot,
                reference_slot=reference_slot,
                top_k=plan["top_k"],
            )
        else:
            retrieval_response = retrieve_project_chunks(
                project_id=project_id,
                request=RetrieveRequest(
                    query=query,
                    top_k=plan["top_k"],
                    platform=plan["platform"],  # type: ignore[arg-type]
                    slot=plan["slot"],  # type: ignore[arg-type]
                    source_type=plan["source_type"],  # type: ignore[arg-type]
                ),
            )
        retrieved_context = _retrieved_context_text(retrieval_response.results)
        citations = [_citation_from_chunk(chunk) for chunk in retrieval_response.results]

        if not citations:
            citations = _fallback_context_citations(project, structured_context)
    else:
        citations = _fallback_context_citations(project, structured_context)

    if recent_messages:
        history_text = _history_text(recent_messages)
        if history_text and retrieved_context:
            retrieved_context = f"Recent conversation:\n{history_text}\n\n{retrieved_context}"
        elif history_text:
            retrieved_context = f"Recent conversation:\n{history_text}"

    return RagContext(
        project_id=project_id,
        intent=intent,
        structured_context=structured_context,
        retrieved_context=retrieved_context,
        citations=citations,
    )


def build_grounded_prompt_inputs(
    project_id: str,
    message: str,
    recent_messages: list[ChatMessage] | None = None,
) -> dict[str, Any]:
    rag_context = build_rag_context(
        project_id=project_id,
        message=message,
        recent_messages=recent_messages,
    )

    return {
        "intent": rag_context.intent,
        "structured_context": rag_context.structured_context,
        "retrieved_context": rag_context.retrieved_context,
        "citations": [citation.model_dump() for citation in rag_context.citations],
        "history_text": _history_text(recent_messages or []),
    }


def build_direct_answer_if_possible(
    project_id: str,
    message: str,
    rag_context: RagContext,
) -> dict[str, Any] | None:
    normalized_message = _normalize(message)
    project = get_project_detail_record(project_id)

    if project is None:
        raise RagContextProjectNotFoundError("Project not found.")

    content_items = _content_items(project)

    if _requires_gemini_rag_reasoning(normalized_message):
        return None

    if _is_missing_metadata_question(normalized_message):
        return _missing_metadata_answer(project, content_items)

    if _is_creator_question(normalized_message):
        return _creator_answer(project, content_items)

    if _is_facebook_data_question(normalized_message):
        return _extracted_data_answer(project, content_items, platform="facebook")

    if _is_facebook_crosspost_question(normalized_message):
        return _facebook_crosspost_answer(get_metric_summary(project_id))

    if _is_combined_meta_question(normalized_message):
        return _combined_meta_answer(get_metric_summary(project_id))

    if _is_metric_comparison_question(normalized_message):
        return _generic_metric_comparison_answer(project, content_items, normalized_message)

    if _is_engagement_metric_question(normalized_message):
        return _generic_engagement_rates_answer(project, content_items)

    return None


def _content_insight_lines(content: ContentInsight) -> list[str]:
    lines = [
        "",
        f"{content.label} - {_platform_label(content.platform)}:",
        f"- Hook type: {content.hook_analysis.hook_type}",
        f"- Hook score: {content.hook_analysis.hook_score}/10",
        f"- Overall insight score: {content.scores.overall_score}/10",
        f"- Strengths: {_display_field_list(content.strengths)}",
        f"- Missing metadata: {_display_field_list(content.missing_metadata)}",
        f"- Metadata Confidence: {content.metric_confidence_note}",
    ]

    if content.top_improvement:
        lines.append(f"- Top improvement: {content.top_improvement}")

    return lines


def _comparison_insight_lines(comparison: ComparisonInsight) -> list[str]:
    lines = [
        "",
        "Comparison:",
        f"- Confirmed metric winner: {_display_value(comparison.confirmed_metric_winner)}",
        f"- Hook winner: {_display_value(comparison.hook_winner)}",
        f"- Overall insight winner: {_display_value(comparison.overall_insight_winner)}",
        f"- Main reason: {comparison.main_reason}",
        f"- Confidence note: {comparison.confidence_note}",
        f"- Recommendations: {_display_field_list(comparison.top_recommendations)}",
    ]

    if comparison.example_rewrite_for_content_2:
        lines.append(
            f"- Example rewrite: {comparison.example_rewrite_for_content_2}"
        )

    return lines


def _creator_insight_summary_answer(
    project_id: str,
    project: dict[str, Any],
    rag_context: RagContext,
) -> dict[str, Any] | None:
    summary = _safe_creator_insight_summary(project_id)

    if summary is None:
        return None

    lines = ["Creator Insight Summary:"]

    for content in (summary.content_1, summary.content_2):
        if content is None:
            continue

        lines.extend(
            [
                f"- {content.label} ({_platform_label(content.platform)}): "
                f"Creator Insight Score {content.scores.overall_score}/10; "
                f"Hook Analysis {content.hook_analysis.hook_type} "
                f"({content.hook_analysis.hook_score}/10).",
                f"  Strengths: {_display_field_list(content.strengths)}.",
                f"  Missing metadata: {_display_field_list(content.missing_metadata)}.",
            ]
        )

    lines.extend(
        [
            "Comparison:",
            f"- Confirmed metric winner: {_display_value(summary.comparison.confirmed_metric_winner)}.",
            f"- Hook winner: {_display_value(summary.comparison.hook_winner)}.",
            f"- Overall insight winner: {_display_value(summary.comparison.overall_insight_winner)}.",
            f"- Main reason: {summary.comparison.main_reason}",
            f"- Metadata Confidence: {summary.comparison.confidence_note}",
            "Scores are heuristic creator-review signals, not guaranteed performance predictions.",
        ]
    )

    return {
        "answer": "\n".join(lines),
        "citations": _direct_citations(project, rag_context),
    }


def _hook_analysis_answer(
    project_id: str,
    project: dict[str, Any],
    rag_context: RagContext,
) -> dict[str, Any] | None:
    summary = _safe_creator_insight_summary(project_id)

    if summary is None:
        return None

    lines = ["Hook Analysis:"]

    for content in (summary.content_1, summary.content_2):
        if content is None:
            continue

        hook = content.hook_analysis
        lines.extend(
            [
                f"- {content.label} ({_platform_label(content.platform)}): "
                f"{hook.hook_type}, {hook.hook_score}/10.",
                f"  Reason: {hook.clarity_reason}",
                f"  Hook text: {_display_value(hook.hook_text)}",
            ]
        )

    lines.append(
        f"Stronger opening: {_display_value(summary.comparison.hook_winner)}."
    )

    if summary.comparison.example_rewrite_for_content_2:
        lines.append(
            f"Suggested rewrite: {summary.comparison.example_rewrite_for_content_2}"
        )

    return {
        "answer": "\n".join(lines),
        "citations": _direct_citations(project, rag_context),
    }


def _stronger_content_answer(
    project_id: str,
    project: dict[str, Any],
    rag_context: RagContext,
) -> dict[str, Any] | None:
    summary = _safe_creator_insight_summary(project_id)

    if summary is None:
        return None

    lines = [
        "Stronger content assessment:",
        f"- Confirmed metric winner: {_display_value(summary.comparison.confirmed_metric_winner)}.",
        f"- Hook winner: {_display_value(summary.comparison.hook_winner)}.",
        f"- Overall insight winner: {_display_value(summary.comparison.overall_insight_winner)}.",
        f"- Reason: {summary.comparison.main_reason}",
        f"- Metadata Confidence: {summary.comparison.confidence_note}",
        "This separates confirmed metric performance from heuristic content-quality signals.",
    ]

    return {
        "answer": "\n".join(lines),
        "citations": _direct_citations(project, rag_context),
    }


def _rewrite_answer(
    project_id: str,
    project: dict[str, Any],
    rag_context: RagContext,
) -> dict[str, Any] | None:
    summary = _safe_creator_insight_summary(project_id)

    if summary is None:
        return None

    comparison = summary.comparison
    target = summary.content_2
    source = summary.content_1
    lines = ["Improvement direction for Content 2:"]

    if target is not None:
        lines.append(
            f"- Diagnosis: Content 2 uses a {target.hook_analysis.hook_type} hook "
            f"with a {target.hook_analysis.hook_score}/10 hook score."
        )

    if source is not None:
        lines.append(
            f"- What to copy from Content 1: {source.hook_analysis.clarity_reason}"
        )

    if comparison.top_recommendations:
        lines.append(
            f"- What to improve: {_display_field_list(comparison.top_recommendations)}."
        )

    if comparison.example_rewrite_for_content_2:
        lines.append(f"- Example rewrite: {comparison.example_rewrite_for_content_2}")
    else:
        lines.append("- Example rewrite: Unavailable because the content topic is unavailable.")

    lines.append(
        "- Why this should help: it makes the opening more specific and easier to judge in the first seconds."
    )

    return {
        "answer": "\n".join(lines),
        "citations": _direct_citations(project, rag_context),
    }


def _improvement_answer(
    project_id: str,
    project: dict[str, Any],
    rag_context: RagContext,
) -> dict[str, Any] | None:
    summary = _safe_creator_insight_summary(project_id)

    if summary is None:
        return None

    content_1 = summary.content_1
    content_2 = summary.content_2
    comparison = summary.comparison
    lines = ["Improvement plan:"]

    if content_2 is not None:
        lines.append(
            f"- Diagnosis: Content 2 ({_platform_label(content_2.platform)}) has "
            f"a Creator Insight Score of {content_2.scores.overall_score}/10 and "
            f"a {content_2.hook_analysis.hook_type} hook."
        )

    if content_1 is not None:
        lines.append(
            f"- What worked in Content 1: {_display_field_list(content_1.strengths)}."
        )

    if comparison.top_recommendations:
        lines.append(
            f"- What to improve: {_display_field_list(comparison.top_recommendations)}."
        )

    if comparison.example_rewrite_for_content_2:
        lines.append(f"- Example rewrite: {comparison.example_rewrite_for_content_2}")

    lines.append(
        f"- Metadata Confidence: {comparison.confidence_note}"
    )
    lines.append(
        "- Why this should help: the changes make the hook, payoff, and audience signal easier to understand before viewers decide to scroll."
    )

    return {
        "answer": "\n".join(lines),
        "citations": _direct_citations(project, rag_context),
    }


def _platform_metadata_section(platform_label: str, metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return f"{platform_label} metadata:\nStatus: Unavailable"

    description_label = (
        "Caption" if str(metadata.get("platform")) == "instagram" else "Description"
    )
    lines = [
        f"{platform_label} metadata:",
        f"Slot: {_display_value(metadata.get('slot'))}",
        f"Platform: {_platform_label(str(metadata.get('platform')))}",
        f"Title: {_display_value(metadata.get('title'))}",
        f"{description_label}: {_display_long_text(metadata.get('caption') or metadata.get('description'))}",
        f"Creator: {_display_value(metadata.get('creator'))}",
        "Confirmed public metrics:",
        f"Views: {_display_number(metadata.get('views'))}",
        f"Likes: {_display_number(metadata.get('likes'))}",
        f"Reactions: {_display_number(metadata.get('reactions'))}",
        f"Comments: {_display_number(metadata.get('comments'))}",
        f"Shares: {_display_number(metadata.get('shares'))}",
        f"Engagement rate: {_display_percent(metadata.get('engagement_rate'))}",
        f"Follower count: {_display_number(metadata.get('follower_count'))}",
        f"Subscriber count: {_display_number(metadata.get('subscriber_count'))}",
        f"Duration seconds: {_display_number(metadata.get('duration_seconds'))}",
        f"Upload date: {_display_value(metadata.get('upload_date'))}",
        f"Hashtags: {_display_hashtags(metadata.get('hashtags'))}",
        f"Transcript language: {_language_label(metadata.get('detected_language') or metadata.get('transcript_language'))}",
        f"Transcript source: {_transcript_source_label(metadata.get('transcript_source'))}",
        f"Available fields: {_display_field_list(_metadata_available_fields(metadata))}",
        f"Missing fields: {_display_field_list(_metadata_missing_fields(metadata))}",
        f"Metric note: {_display_value(metadata.get('metric_source_note'))}",
        f"Transcript note: {_display_value(metadata.get('transcript_source_note'))}",
        "Rule: missing confirmed public metrics are unavailable and not estimated.",
    ]

    if str(metadata.get("platform")) == "instagram":
        lines.append(
            "Instagram caveat: Public extraction may not include "
            "Facebook-crossposted reactions or comments."
        )

    return "\n".join(lines)


def _retrieved_context_text(chunks: list[RetrievedChunk]) -> str:
    blocks = []

    for index, chunk in enumerate(chunks, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[Source {index}] {chunk.citation_label}",
                    chunk.text,
                ]
            )
        )

    return "\n\n".join(blocks)


def _citation_from_chunk(chunk: RetrievedChunk) -> Citation:
    return Citation(
        platform=_platform_label(chunk.platform),
        source_type=chunk.source_type,
        citation_label=chunk.citation_label,
        text=chunk.text,
        score=chunk.score,
    )


def _metadata_citations(project: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []

    for metadata in project.get("content_items", []):
        if not isinstance(metadata, dict):
            continue

        platform_label = _content_label(metadata)
        citations.append(
            Citation(
                platform=platform_label,
                source_type="metadata",
                citation_label=f"{platform_label} metadata",
                text=_platform_metadata_section(platform_label, metadata),
                score=None,
            )
        )

    return citations


def _fallback_context_citations(
    project: dict[str, Any],
    structured_context: str,
) -> list[Citation]:
    citations = _metadata_citations(project)
    insight_context = _insight_context_from_structured_context(structured_context)

    if insight_context:
        citations.append(
            Citation(
                platform="CreatorLens AI",
                source_type="insight",
                citation_label="Creator Insight Summary",
                text=_compact_text(insight_context, max_length=1200),
                score=None,
            )
        )

    return citations


def _insight_context_from_structured_context(structured_context: str) -> str:
    marker = "Creator Insight Summary:"
    marker_index = structured_context.find(marker)

    if marker_index < 0:
        return ""

    return structured_context[marker_index:].strip()


def _metric_citations(summary: MetricSummaryResponse) -> list[Citation]:
    citations = [
        Citation(
            platform="Meta",
            source_type="metadata",
            citation_label="Metric Source Resolver Summary",
            text=build_metric_summary_text(summary),
            score=None,
        )
    ]

    for record in summary.records:
        citations.append(
            Citation(
                platform=_platform_label(record.source_platform),
                source_type="metadata",
                citation_label=f"{_platform_label(record.source_platform)} {record.metric_scope} metrics",
                text=_metric_record_summary(record),
                score=None,
            )
        )

    return citations


def build_metric_summary_text(summary: MetricSummaryResponse) -> str:
    return "\n".join(
        [
            "Metric Source Resolver Summary:",
            f"YouTube native status: {summary.youtube_status}",
            f"Instagram native status: {summary.instagram_native_status}",
            f"Facebook cross-post status: {summary.facebook_crosspost_status}",
            f"Combined Meta status: {summary.combined_meta_status}",
            f"Combined Meta views: {_display_number(summary.combined_meta_views)}",
            f"Combined Meta interactions: {_display_number(summary.combined_meta_interactions)}",
            f"Combined Meta engagement rate: {_display_percent(summary.combined_meta_engagement_rate)}",
            "Unavailable metrics are not estimated.",
        ]
    )


def _generic_engagement_rates_answer(
    project: dict[str, Any],
    content_items: list[dict[str, Any]],
) -> dict[str, Any]:
    lines = [
        "Confirmed public engagement rates:",
        *[
            f"- {_content_label(item)}: {_display_percent(item.get('engagement_rate'))}."
            for item in content_items
        ],
        "Unavailable engagement rates are not estimated.",
    ]

    return {
        "answer": "\n".join(lines),
        "citations": _metadata_citations(project),
    }


def _creator_answer(
    project: dict[str, Any],
    content_items: list[dict[str, Any]],
) -> dict[str, Any]:
    lines = [
        "Creators from confirmed public metadata:",
        *[
            f"- {_content_label(item)} creator: {_display_value(item.get('creator'))}."
            for item in content_items
        ],
        "Unavailable creator or follower/subscriber fields are not estimated.",
    ]

    return {
        "answer": "\n".join(lines),
        "citations": _metadata_citations(project),
    }


def _missing_metadata_answer(
    project: dict[str, Any],
    content_items: list[dict[str, Any]],
) -> dict[str, Any]:
    lines = ["Metadata Availability:"]

    for item in content_items:
        available_fields = _metadata_available_fields(item)
        missing_fields = _metadata_missing_fields(item)
        lines.append(
            f"- {_content_label(item)} available fields: "
            f"{_display_field_list(available_fields)}; missing fields: "
            f"{_display_field_list(missing_fields)}."
        )

    lines.append(
        "Unavailable fields are usually limited by public platform extraction, "
        "privacy, or missing transcript evidence. Missing fields are not estimated."
    )

    return {
        "answer": "\n".join(lines),
        "citations": _metadata_citations(project),
    }


def _extracted_data_answer(
    project: dict[str, Any],
    content_items: list[dict[str, Any]],
    platform: str,
) -> dict[str, Any]:
    matching_items = [
        item for item in content_items if str(item.get("platform")) == platform
    ]
    selected_items = matching_items or content_items
    lines = ["Confirmed public metadata extracted:"]

    for item in selected_items:
        lines.append(
            f"- {_content_label(item)} available fields: "
            f"{_display_field_list(_metadata_available_fields(item))}; "
            f"missing fields: {_display_field_list(_metadata_missing_fields(item))}."
        )

    lines.append("Unavailable fields are not estimated.")

    return {
        "answer": "\n".join(lines),
        "citations": _metadata_citations(project),
    }


def _generic_metric_comparison_answer(
    project: dict[str, Any],
    content_items: list[dict[str, Any]],
    message: str,
) -> dict[str, Any]:
    metric_name = _comparison_metric_name(message)
    values = [
        (item, _comparison_metric_value(item, metric_name))
        for item in content_items
    ]
    metric_label = _metric_display_label(metric_name)
    lines = [f"Confirmed public {metric_label} comparison:"]

    for item, value in values:
        lines.append(f"- {_content_label(item)}: {_display_metric_value(metric_name, value)}.")

    available_values = [(item, value) for item, value in values if value is not None]

    if len(available_values) < len(values):
        missing_labels = [
            _content_label(item)
            for item, value in values
            if value is None
        ]
        lines.append(
            "Comparison is limited because "
            f"{metric_label} is unavailable for {', '.join(missing_labels)}."
        )
    elif len(available_values) >= 2:
        winner, winner_value = max(available_values, key=lambda pair: pair[1])
        tied_items = [
            item for item, value in available_values if value == winner_value
        ]

        if len(tied_items) > 1:
            lines.append("The confirmed public values are tied.")
        else:
            lines.append(
                f"{_content_label(winner)} has the higher confirmed public "
                f"{metric_label}."
            )

    lines.append("Unavailable metrics are not estimated.")

    return {
        "answer": "\n".join(lines),
        "citations": _metadata_citations(project),
    }


def _instagram_creator_answer(
    project: dict[str, Any],
    summary: MetricSummaryResponse,
) -> dict[str, Any]:
    instagram_metadata = project.get("instagram") if isinstance(project, dict) else None
    instagram_native = _latest_record(summary.records, "instagram", "native")
    creator = (
        _display_value(instagram_metadata.get("creator"))
        if isinstance(instagram_metadata, dict)
        else "Unavailable"
    )
    followers = (
        _display_number(instagram_native.followers)
        if instagram_native and instagram_native.followers is not None
        else "Unavailable"
    )
    source_method = (
        _source_method_label(instagram_native.source_method)
        if instagram_native
        else "no metric source record"
    )
    answer = "\n".join(
        [
            f"Instagram creator: {creator}.",
            f"Instagram follower count: {followers}.",
            f"Follower count source: {source_method}.",
            "If the follower count is unavailable, CreatorLens AI will not estimate it unless Verified Metrics provide it.",
        ]
    )

    return {
        "answer": answer,
        "citations": _metric_citations(summary),
    }


def _engagement_rates_answer(summary: MetricSummaryResponse) -> dict[str, Any]:
    youtube_native = _latest_record(summary.records, "youtube", "native")
    instagram_native = _latest_record(summary.records, "instagram", "native")
    facebook_crosspost = _latest_record(summary.records, "facebook", "cross_post")
    lines = [
        f"YouTube confirmed public engagement rate: {_record_percent(youtube_native)}.",
        f"Instagram confirmed public engagement rate: {_record_percent(instagram_native)}.",
        f"Facebook cross-post engagement rate: {_record_percent(facebook_crosspost)}.",
        f"Combined Meta engagement rate: {_display_percent(summary.combined_meta_engagement_rate)}.",
        "Unavailable metrics are not estimated.",
    ]

    return {
        "answer": "\n".join(lines),
        "citations": _metric_citations(summary),
    }


def _facebook_crosspost_answer(summary: MetricSummaryResponse) -> dict[str, Any]:
    facebook_crosspost = _latest_record(summary.records, "facebook", "cross_post")

    if facebook_crosspost is None:
        answer = "No Facebook cross-post metrics are connected yet."
    else:
        answer = "\n".join(
            [
                f"Facebook cross-post views: {_display_number(facebook_crosspost.views)}.",
                f"Facebook cross-post reactions: {_display_number(facebook_crosspost.reactions)}.",
                f"Facebook cross-post comments: {_display_number(facebook_crosspost.comments)}.",
                f"Facebook cross-post shares: {_display_number(facebook_crosspost.shares)}.",
                f"Facebook cross-post engagement rate: {_display_percent(facebook_crosspost.engagement_rate)}.",
                f"Source: {_source_method_label(facebook_crosspost.source_method)}.",
            ]
        )

    return {
        "answer": answer,
        "citations": _metric_citations(summary),
    }


def _combined_meta_answer(summary: MetricSummaryResponse) -> dict[str, Any]:
    if summary.combined_meta_engagement_rate is not None:
        answer = "\n".join(
            [
                f"Combined Meta views: {_display_number(summary.combined_meta_views)}.",
                f"Combined Meta interactions: {_display_number(summary.combined_meta_interactions)}.",
                f"Combined Meta engagement rate: {_display_percent(summary.combined_meta_engagement_rate)}.",
                "Combined Meta Metrics use available Instagram native metrics and verified Facebook cross-post metrics only.",
            ]
        )
    else:
        missing = _combined_missing_fields(summary) or "required Instagram/Facebook views or interaction metrics"
        answer = (
            "Combined Meta engagement is unavailable because "
            f"{missing} are not provided. Unavailable metrics are not estimated."
        )

    return {
        "answer": answer,
        "citations": _metric_citations(summary),
    }


def _safe_creator_insight_summary(
    project_id: str,
) -> CreatorInsightSummaryResponse | None:
    try:
        return get_creator_insight_summary(project_id)
    except Exception:
        return None


def _direct_citations(
    project: dict[str, Any],
    rag_context: RagContext,
) -> list[Citation]:
    if rag_context.citations:
        return rag_context.citations

    return _metadata_citations(project)


def _performance_comparison_answer(summary: MetricSummaryResponse) -> dict[str, Any]:
    youtube_native = _latest_record(summary.records, "youtube", "native")
    instagram_native = _latest_record(summary.records, "instagram", "native")
    youtube_rate_value = _record_engagement_rate(youtube_native)
    instagram_rate_value = _record_engagement_rate(instagram_native)
    youtube_rate = _record_percent(youtube_native)
    instagram_rate = _record_percent(instagram_native)

    if youtube_rate_value is None or instagram_rate_value is None:
        comparison = (
            "A confirmed engagement winner is unavailable because one or both "
            "native engagement rates are unavailable."
        )
    elif youtube_rate_value > instagram_rate_value:
        comparison = (
            "YouTube has stronger confirmed public engagement based on the "
            "available extracted metrics."
        )
    elif instagram_rate_value > youtube_rate_value:
        comparison = (
            "Instagram has stronger confirmed public engagement based on the "
            "available extracted metrics."
        )
    else:
        comparison = (
            "The compared platforms have the same confirmed public engagement "
            "rate based on the available extracted metrics."
        )

    answer = "\n".join(
        [
            comparison,
            f"YouTube confirmed public engagement rate: {youtube_rate}.",
            f"Instagram confirmed public engagement rate: {instagram_rate}.",
            "Instagram combined Meta performance may be incomplete without Facebook cross-post metrics.",
            "Unavailable metrics are not estimated.",
        ]
    )

    return {
        "answer": answer,
        "citations": _metric_citations(summary),
    }


def _latest_record(
    records: list[MetricSourceRecord],
    source_platform: str,
    metric_scope: str,
) -> MetricSourceRecord | None:
    verified_methods = {"user_verified", "manual_entry", "screenshot_verified"}

    for record in records:
        if (
            record.source_platform == source_platform
            and record.metric_scope == metric_scope
            and record.source_method in verified_methods
        ):
            return record

    for record in records:
        if record.source_platform == source_platform and record.metric_scope == metric_scope:
            return record

    return None


def _metric_record_summary(record: MetricSourceRecord | None) -> str:
    if record is None:
        return "unavailable."

    return (
        f"views {_display_number(record.views)}; "
        f"likes {_display_number(record.likes)}; "
        f"reactions {_display_number(record.reactions)}; "
        f"comments {_display_number(record.comments)}; "
        f"shares {_display_number(record.shares)}; "
        f"followers {_display_number(record.followers)}; "
        f"engagement rate {_display_percent(record.engagement_rate)}; "
        f"source {_source_method_label(record.source_method)}; "
        f"confidence {record.confidence}."
    )


def _record_percent(record: MetricSourceRecord | None) -> str:
    if record is None:
        return "Unavailable"

    return _display_percent(record.engagement_rate)


def _record_engagement_rate(record: MetricSourceRecord | None) -> float | None:
    if record is None or isinstance(record.engagement_rate, bool):
        return None

    if isinstance(record.engagement_rate, int | float):
        return float(record.engagement_rate)

    return None


def _combined_missing_fields(summary: MetricSummaryResponse) -> str:
    combined = next(
        (
            item
            for item in summary.completeness
            if item.label == "Combined Meta Metrics"
        ),
        None,
    )

    if combined is None or not combined.missing_fields:
        return ""

    return ", ".join(field.replace("_", " ") for field in combined.missing_fields)


def _source_method_label(source_method: str) -> str:
    if source_method == "public_extractor":
        return "public extractor"

    if source_method == "user_verified":
        return "user verified"

    if source_method == "manual_entry":
        return "manual entry"

    if source_method == "screenshot_verified":
        return "screenshot verified"

    if source_method == "meta_api":
        return "Meta API"

    return source_method


def _content_items(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in project.get("content_items", [])
        if isinstance(item, dict)
    ]


def _metadata_available_fields(item: dict[str, Any]) -> list[str]:
    field_values = {
        "transcript": bool(item.get("transcript_available")),
        "views": item.get("views") is not None,
        "likes": item.get("likes") is not None,
        "reactions": item.get("reactions") is not None,
        "comments": item.get("comments") is not None,
        "shares": item.get("shares") is not None,
        "creator": _display_value(item.get("creator")) != "Unavailable",
        "follower_count": item.get("follower_count") is not None,
        "subscriber_count": item.get("subscriber_count") is not None,
        "hashtags": bool(item.get("hashtags")),
        "upload_date": item.get("upload_date") is not None,
        "duration_seconds": item.get("duration_seconds") is not None,
        "engagement_rate": item.get("engagement_rate") is not None,
    }

    return [
        field_name
        for field_name, is_available in field_values.items()
        if is_available
    ]


def _metadata_missing_fields(item: dict[str, Any]) -> list[str]:
    explicit_missing = item.get("missing_fields")

    if isinstance(explicit_missing, list):
        fields = [
            field
            for field in explicit_missing
            if isinstance(field, str) and field.strip()
        ]

        if fields:
            return fields

    available_fields = set(_metadata_available_fields(item))
    expected_fields = {
        "transcript",
        "views",
        "creator",
        "comments",
        "hashtags",
        "upload_date",
        "duration_seconds",
        "engagement_rate",
    }

    if item.get("platform") == "facebook":
        expected_fields.update({"reactions", "shares"})
    else:
        expected_fields.add("likes")

    if item.get("follower_count") is None and item.get("subscriber_count") is None:
        expected_fields.add("follower_count/subscriber_count")

    return sorted(expected_fields - available_fields)


def _display_field_list(fields: list[str]) -> str:
    clean_fields = [
        field.replace("_", " ")
        for field in fields
        if isinstance(field, str) and field.strip()
    ]

    return ", ".join(clean_fields) if clean_fields else "Unavailable"


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _display_metric_value(metric_name: str, value: float | None) -> str:
    if value is None:
        return "Unavailable"

    if metric_name == "engagement_rate":
        return _display_percent(value)

    return _display_number(value)


def _comparison_metric_value(
    item: dict[str, Any],
    metric_name: str,
) -> float | None:
    if metric_name == "follower_or_subscriber_count":
        follower_count = _numeric_value(item.get("follower_count"))

        if follower_count is not None:
            return follower_count

        return _numeric_value(item.get("subscriber_count"))

    if metric_name == "interactions":
        return _interaction_count(item)

    return _numeric_value(item.get(metric_name))


def _interaction_count(item: dict[str, Any]) -> float | None:
    platform = str(item.get("platform") or "")
    values = (
        (
            _numeric_value(item.get("reactions")),
            _numeric_value(item.get("comments")),
            _numeric_value(item.get("shares")),
        )
        if platform == "facebook"
        else (
            _numeric_value(item.get("likes")),
            _numeric_value(item.get("comments")),
        )
    )
    available_values = [value for value in values if value is not None]

    if not available_values:
        return None

    return float(sum(available_values))


def _metric_display_label(metric_name: str) -> str:
    if metric_name == "engagement_rate":
        return "engagement rate"

    if metric_name == "follower_or_subscriber_count":
        return "follower/subscriber count"

    return metric_name.replace("_", " ")


def _comparison_metric_name(message: str) -> str:
    if "follower" in message or "subscriber" in message:
        return "follower_or_subscriber_count"

    if "interaction" in message:
        return "interactions"

    if "like" in message:
        return "likes"

    if "comment" in message:
        return "comments"

    if "reaction" in message:
        return "reactions"

    if "share" in message:
        return "shares"

    if "view" in message:
        return "views"

    return "engagement_rate"


def _is_creator_question(message: str) -> bool:
    return (
        "creator" in message
        or "who is" in message
        or "who made" in message
    )


def _requires_gemini_rag_reasoning(message: str) -> bool:
    return (
        _is_insight_summary_question(message)
        or _is_rewrite_request(message)
        or _is_improvement_question(message)
        or _is_hook_analysis_question(message)
        or _is_stronger_content_question(message)
        or _is_performance_comparison_question(message)
        or "explain the difference" in message
        or "strategic recommendation" in message
        or "strategic recommendations" in message
        or "what should the creator do next" in message
        or "create a new hook" in message
        or "improve the caption" in message
    )


def _is_insight_summary_question(message: str) -> bool:
    return (
        "creator insight summary" in message
        or "insight summary" in message
        or "creator insight score" in message
        or "insight score" in message
        or "what is the score" in message
        or "scores" in message
    )


def _is_hook_analysis_question(message: str) -> bool:
    return (
        "hook" in message
        or "first seconds" in message
        or "first few seconds" in message
        or "opening" in message
        or "opening line" in message
    )


def _is_rewrite_request(message: str) -> bool:
    return (
        "rewrite" in message
        or "opening line" in message
        or "caption rewrite" in message
        or "rewrite the opening" in message
    )


def _is_improvement_question(message: str) -> bool:
    return (
        "improve" in message
        or "improvement" in message
        or "suggest" in message
        or "suggestion" in message
        or "recommendation" in message
        or "recommendations" in message
        or "make better" in message
    )


def _is_stronger_content_question(message: str) -> bool:
    return (
        "which content is stronger" in message
        or "which is stronger" in message
        or "stronger opening" in message
        or "performed better" in message
        or "stronger engagement" in message
        or "why" in message and ("better" in message or "stronger" in message)
    )


def _is_missing_metadata_question(message: str) -> bool:
    return (
        "metadata is missing" in message
        or "metadata missing" in message
        or "missing metadata" in message
        or "what metadata" in message
        or "missing or unavailable" in message
        or "unavailable" in message and "metadata" in message
    )


def _is_facebook_data_question(message: str) -> bool:
    return (
        "facebook" in message
        and (
            "what data" in message
            or "what could be extracted" in message
            or "extracted from facebook" in message
            or "available from facebook" in message
        )
    )


def _is_metric_comparison_question(message: str) -> bool:
    comparison_words = (
        "more",
        "higher",
        "stronger",
        "compare",
        "outperform",
        "performed better",
        "has better",
    )
    metric_words = (
        "views",
        "likes",
        "comments",
        "reactions",
        "shares",
        "followers",
        "follower count",
        "subscriber",
        "subscriber count",
        "interactions",
        "engagement",
        "performance",
    )

    return any(word in message for word in comparison_words) and any(
        word in message for word in metric_words
    )


def _is_creator_follower_question(message: str) -> bool:
    return "instagram" in message and (
        "creator" in message
        or "who is" in message
        or "follower count" in message
        or "followers" in message
    )


def _is_engagement_metric_question(message: str) -> bool:
    return (
        "engagement rate" in message
        or "engagement of each" in message
        or "metrics" in message
        or "views" in message
        or "likes" in message
        or "comments" in message
    )


def _is_facebook_crosspost_question(message: str) -> bool:
    return "cross-post" in message or "cross post" in message


def _is_combined_meta_question(message: str) -> bool:
    return "combined meta" in message or "meta engagement" in message


def _is_performance_comparison_question(message: str) -> bool:
    return (
        "why" in message
        and ("youtube" in message or "instagram" in message)
        and ("engagement" in message or "performance" in message)
    ) or "more engagement than instagram" in message


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())


def _history_text(messages: list[ChatMessage]) -> str:
    if not messages:
        return ""

    recent_messages = messages[-6:]
    return "\n".join(
        f"{message.role}: {_compact_text(message.content, max_length=240)}"
        for message in recent_messages
    )


def _platform_label(platform: str) -> str:
    if platform == "youtube":
        return "YouTube"

    if platform == "instagram":
        return "Instagram"

    if platform == "facebook":
        return "Facebook"

    if platform == "meta":
        return "Meta"

    return platform


def _content_label(metadata: dict[str, Any]) -> str:
    slot = metadata.get("slot")
    platform = _platform_label(str(metadata.get("platform") or ""))

    if slot == "content_1":
        return f"Content 1 - {platform}"

    if slot == "content_2":
        return f"Content 2 - {platform}"

    return platform


def _display_value(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return "Unavailable"


def _display_long_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Unavailable"

    return _compact_text(value.strip(), max_length=500)


def _display_number(value: Any) -> str:
    if isinstance(value, bool):
        return "Unavailable"

    if isinstance(value, int):
        return f"{value:,}"

    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"

    return "Unavailable"


def _display_percent(value: Any) -> str:
    if isinstance(value, bool):
        return "Unavailable"

    if isinstance(value, int | float):
        return f"{float(value):.2f}%"

    return "Unavailable"


def _display_hashtags(value: Any) -> str:
    if not isinstance(value, list):
        return "Unavailable"

    tags = [
        f"#{tag.strip().lstrip('#')}"
        for tag in value
        if isinstance(tag, str) and tag.strip()
    ]

    return ", ".join(tags) if tags else "Unavailable"


def _language_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Unavailable"

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


def _transcript_source_label(value: Any) -> str:
    if value == "platform_captions":
        return "Captions"

    if value == "deepgram_multilingual":
        return "Deepgram multilingual"

    if value == "apify_youtube_transcript":
        return "Apify YouTube transcript"

    if value == "unavailable":
        return "Unavailable"

    if isinstance(value, str) and value.strip():
        return value.strip()

    return "Unavailable"


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
