from typing import Any

from app.models.chat import ChatMessage, Citation, RagContext
from app.models.rag import RetrieveRequest, RetrievedChunk
from app.rag.query_router import classify_question, get_retrieval_plan
from app.rag.retrieval_service import retrieve_project_chunks
from app.services.storage_service import get_project_detail_record


class RagContextProjectNotFoundError(Exception):
    """Raised when RAG context is requested for a missing project."""


class RagContextValidationError(Exception):
    """Raised when RAG context input is invalid."""


def build_structured_metadata_context(project_id: str) -> str:
    project = get_project_detail_record(project_id)

    if project is None:
        raise RagContextProjectNotFoundError("Project not found.")

    sections = [
        _platform_metadata_section("YouTube", project.get("youtube")),
        _platform_metadata_section("Instagram", project.get("instagram")),
    ]

    return "\n\n".join(sections)


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
        retrieval_response = retrieve_project_chunks(
            project_id=project_id,
            request=RetrieveRequest(
                query=query,
                top_k=plan["top_k"],
                platform=plan["platform"],  # type: ignore[arg-type]
                source_type=plan["source_type"],  # type: ignore[arg-type]
            ),
        )
        retrieved_context = _retrieved_context_text(retrieval_response.results)
        citations = [_citation_from_chunk(chunk) for chunk in retrieval_response.results]
    else:
        citations = _metadata_citations(project)

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


def _platform_metadata_section(platform_label: str, metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return f"{platform_label} metadata:\nStatus: Unavailable"

    description_label = "Caption" if platform_label == "Instagram" else "Description"
    lines = [
        f"{platform_label} metadata:",
        f"Title: {_display_value(metadata.get('title'))}",
        f"{description_label}: {_display_long_text(metadata.get('description'))}",
        f"Creator: {_display_value(metadata.get('creator'))}",
        f"Views: {_display_number(metadata.get('views'))}",
        f"Likes: {_display_number(metadata.get('likes'))}",
        f"Comments: {_display_number(metadata.get('comments'))}",
        f"Engagement rate: {_display_percent(metadata.get('engagement_rate'))}",
        f"Follower count: {_display_number(metadata.get('follower_count'))}",
        f"Duration seconds: {_display_number(metadata.get('duration_seconds'))}",
        f"Upload date: {_display_value(metadata.get('upload_date'))}",
        f"Hashtags: {_display_hashtags(metadata.get('hashtags'))}",
        f"Metric note: {_display_value(metadata.get('metric_source_note'))}",
    ]

    if platform_label == "Instagram":
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

    for platform_key, platform_label in (
        ("youtube", "YouTube"),
        ("instagram", "Instagram"),
    ):
        metadata = project.get(platform_key)

        if not isinstance(metadata, dict):
            continue

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


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
