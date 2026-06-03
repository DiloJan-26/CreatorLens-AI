import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.models.chat import ChatMessage, ChatStreamRequest, Citation
from app.rag.context_builder import (
    RagContextProjectNotFoundError,
    RagContextValidationError,
    build_direct_answer_if_possible,
    build_rag_context,
)
from app.rag.retrieval_service import RetrievalProjectNotFoundError
from app.services.chat_memory_service import (
    ChatProjectNotFoundError,
    ChatSessionNotFoundError,
    ChatValidationError,
    add_message,
    create_or_get_session,
    get_recent_messages,
)
from app.services.llm_service import LLMConfigurationError, get_llm
from app.services.qdrant_service import QdrantConfigurationError
from app.services.storage_service import save_chat_citations


def build_system_prompt() -> str:
    return "\n".join(
        [
            "You are CreatorLens AI, a creator intelligence assistant.",
            "Use confirmed public metrics, Creator Insight Summary, retrieved transcript/caption/metadata chunks, metadata availability, and conversation memory.",
            "The compared items are Content 1 and Content 2. Use those labels exactly.",
            "Always mention platform names: YouTube, Instagram, or Facebook.",
            "Use confirmed public metrics only and say Unavailable when public data is missing.",
            "Do not invent views, likes, comments, reactions, shares, follower counts, subscriber counts, engagement rates, dates, duration, or transcript details.",
            "Distinguish confirmed metric performance from heuristic content-quality signals such as Hook Analysis and Creator Insight Score.",
            "Creator Insight Scores are heuristic review signals, not guaranteed performance predictions.",
            "If metric data is incomplete, say the comparison is limited.",
            "For Instagram, mention public extraction limitations or Facebook cross-post caveats when relevant.",
            "Do not assume Instagram or Facebook metrics are complete.",
            "If same-platform comparison appears, use Content 1 and Content 2 labels to avoid confusion.",
            "For reasoning questions, give structured insight, not a generic paragraph.",
            "For improvement questions, include diagnosis, what worked, what to change, and an example rewrite.",
            "For hook questions, identify hook type, first-second clarity, payoff, and recommendation.",
            "Use citations only from backend-provided source labels. Do not fabricate citation labels.",
            "The frontend will display citations separately, so do not invent source labels in the answer.",
            "If useful, refer to sources naturally, but citations are provided separately.",
            "Treat the structured Content 1 and Content 2 metadata as the source of truth for content metrics.",
            "Distinguish YouTube, Instagram, Facebook, and Combined Meta Metrics when those appear.",
            "Never claim Instagram underperformed solely from missing views.",
            "Say confirmed public metrics when only public extracted metrics exist.",
            "If Facebook cross-post data is not connected, say combined Meta performance may be incomplete.",
            "Do not invent missing follower counts, subscriber counts, views, comments, duration, or upload dates.",
        ]
    )


def format_chat_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return "No previous conversation."

    recent_messages = messages[-10:]

    return "\n".join(
        f"{message.role}: {_compact_text(message.content, max_length=260)}"
        for message in recent_messages
    )


async def stream_chat_answer(
    project_id: str,
    request: ChatStreamRequest,
) -> AsyncIterator[str]:
    assistant_answer = ""
    session_id = request.session_id
    citations: list[Citation] = []
    settings = get_settings()

    try:
        question = request.message.strip()

        if not question:
            raise ChatValidationError("Message must not be empty.")

        session = create_or_get_session(
            project_id=project_id,
            session_id=session_id,
        )
        session_id = session.session_id

        add_message(
            project_id=project_id,
            session_id=session_id,
            role="user",
            content=question,
        )
        recent_messages = get_recent_messages(
            project_id=project_id,
            session_id=session_id,
            limit=10,
        )
        rag_context = build_rag_context(
            project_id=project_id,
            message=question,
            recent_messages=recent_messages,
        )
        direct_answer = build_direct_answer_if_possible(
            project_id=project_id,
            message=question,
            rag_context=rag_context,
        )

        if direct_answer is not None:
            assistant_answer = str(direct_answer["answer"]).strip()
            citations = [
                citation
                for citation in direct_answer["citations"]
                if isinstance(citation, Citation)
            ]
            yield sse_event(
                "trace",
                _trace_payload(
                    mode="direct_metric_answer",
                    model=settings.llm_model,
                    intent=rag_context.intent,
                    rag_context=rag_context,
                    recent_messages=recent_messages,
                    citations=citations,
                ),
            )

            for token in _direct_answer_tokens(assistant_answer):
                yield sse_event("token", {"text": token})

            assistant_message = add_message(
                project_id=project_id,
                session_id=session_id,
                role="assistant",
                content=assistant_answer,
            )
            save_chat_citations(
                message_id=assistant_message.message_id,
                project_id=project_id,
                session_id=session_id,
                citations=[citation.model_dump() for citation in citations],
            )
            yield sse_event(
                "citations",
                {"citations": [citation.model_dump() for citation in citations]},
            )
            yield sse_event(
                "done",
                {
                    "session_id": session_id,
                    "status": "complete",
                },
            )
            return

        citations = rag_context.citations
        llm = get_llm(streaming=True)
        history_text = format_chat_history(recent_messages)
        prompt_context_summary = _prompt_context_summary(
            rag_context=rag_context,
            history_message_count=len(recent_messages),
            citation_count=len(citations),
        )
        messages = [
            SystemMessage(content=build_system_prompt()),
            HumanMessage(
                content=_human_prompt(
                    question=question,
                    intent=rag_context.intent,
                    structured_context=rag_context.structured_context,
                    retrieved_context=rag_context.retrieved_context,
                    history_text=history_text,
                )
            ),
        ]
        _maybe_debug_prompt(
            messages=messages,
            prompt_context_summary=prompt_context_summary,
        )
        yield sse_event(
            "trace",
            _trace_payload(
                mode="gemini_rag_answer",
                model=settings.llm_model,
                intent=rag_context.intent,
                rag_context=rag_context,
                recent_messages=recent_messages,
                citations=citations,
                prompt_context_summary=prompt_context_summary,
            ),
        )

        async for chunk in llm.astream(messages):
            token = _chunk_text(chunk)

            if not token:
                continue

            assistant_answer += token
            yield sse_event("token", {"text": token})

        assistant_message = add_message(
            project_id=project_id,
            session_id=session_id,
            role="assistant",
            content=assistant_answer.strip()
            or "I could not generate a grounded answer from the available context.",
        )
        save_chat_citations(
            message_id=assistant_message.message_id,
            project_id=project_id,
            session_id=session_id,
            citations=[citation.model_dump() for citation in citations],
        )

        yield sse_event(
            "citations",
            {"citations": [citation.model_dump() for citation in citations]},
        )
        yield sse_event(
            "done",
            {
                "session_id": session_id,
                "status": "complete",
            },
        )
    except (
        ChatProjectNotFoundError,
        RagContextProjectNotFoundError,
        RetrievalProjectNotFoundError,
    ):
        yield sse_event("error", {"message": "Project not found."})
    except ChatSessionNotFoundError:
        yield sse_event("error", {"message": "Chat session not found."})
    except (
        ChatValidationError,
        RagContextValidationError,
    ) as exc:
        yield sse_event("error", {"message": str(exc)})
    except QdrantConfigurationError:
        yield sse_event("error", {"message": "Qdrant is not configured."})
    except LLMConfigurationError as exc:
        yield sse_event("error", {"message": str(exc)})
    except Exception:
        yield sse_event("error", {"message": "Could not stream chat answer."})


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _trace_payload(
    mode: str,
    model: str,
    intent: str,
    rag_context: Any,
    recent_messages: list[ChatMessage],
    citations: list[Citation],
    prompt_context_summary: dict[str, int] | None = None,
) -> dict[str, Any]:
    context_summary = prompt_context_summary or _prompt_context_summary(
        rag_context=rag_context,
        history_message_count=len(recent_messages),
        citation_count=len(citations),
    )

    return {
        "mode": mode,
        "model": model,
        "intent": intent,
        "retrieved_sources": len(citations),
        "has_creator_insights": _has_creator_insights(rag_context),
        "has_structured_metadata": bool(rag_context.structured_context.strip()),
        "has_memory": len(recent_messages) > 1,
        "prompt_context_summary": context_summary,
    }


def _prompt_context_summary(
    rag_context: Any,
    history_message_count: int,
    citation_count: int,
) -> dict[str, int]:
    structured_context = rag_context.structured_context or ""
    retrieved_context = rag_context.retrieved_context or ""
    insight_context = _insight_context(structured_context)

    return {
        "structured_context_chars": len(structured_context),
        "retrieved_context_chars": len(retrieved_context),
        "insight_context_chars": len(insight_context),
        "history_message_count": history_message_count,
        "citation_count": citation_count,
    }


def _has_creator_insights(rag_context: Any) -> bool:
    return bool(_insight_context(rag_context.structured_context or ""))


def _insight_context(structured_context: str) -> str:
    marker = "Creator Insight Summary:"
    marker_index = structured_context.find(marker)

    if marker_index < 0:
        return ""

    return structured_context[marker_index:].strip()


def _maybe_debug_prompt(
    messages: list[SystemMessage | HumanMessage],
    prompt_context_summary: dict[str, int],
) -> None:
    if not get_settings().debug_rag_prompt:
        return

    print(
        "Prompt Context Preview:",
        json.dumps(
            {
                "message_count": len(messages),
                **prompt_context_summary,
            }
        ),
    )


def _human_prompt(
    question: str,
    intent: str,
    structured_context: str,
    retrieved_context: str,
    history_text: str,
) -> str:
    source_context = retrieved_context.strip() or "No retrieved source chunks were needed for this question."
    style_instructions = _answer_style_instructions(intent)

    return "\n\n".join(
        [
            f"User question:\n{question}",
            f"Question intent:\n{intent}",
            f"Recent conversation:\n{history_text}",
            f"Structured metadata context:\n{structured_context}",
            f"Retrieved source context:\n{source_context}",
            "Answer requirements:\n"
            "- Ground every claim in the provided context.\n"
            "- Say Unavailable when public data is missing.\n"
            "- Name Content 1 and Content 2 with their platform names.\n"
            "- Separate confirmed public metrics from heuristic insight scores.\n"
            "- Keep the answer concise and useful for creator analysis.\n"
            "- Do not output fake citation labels.\n"
            f"{style_instructions}",
        ]
    )


def _answer_style_instructions(intent: str) -> str:
    if intent == "performance_reasoning":
        return (
            "- Use this format:\n"
            "1. Confirmed metric comparison\n"
            "2. Hook/content difference\n"
            "3. Caption/CTA difference\n"
            "4. Metadata limitations\n"
            "5. Actionable recommendation"
        )

    if intent == "hook_analysis":
        return (
            "- Use this format:\n"
            "1. Content 1 hook type and evidence\n"
            "2. Content 2 hook type and evidence\n"
            "3. Which opening is stronger and why\n"
            "4. Rewrite suggestion"
        )

    if intent == "improvement_suggestions":
        return (
            "- Use this format:\n"
            "1. Diagnosis\n"
            "2. What worked in stronger content\n"
            "3. What Content 2 should change\n"
            "4. Example rewrite\n"
            "5. Why this may improve engagement"
        )

    if intent == "rewrite_request":
        return (
            "- Focus on the rewritten opening or caption, then briefly explain why "
            "it is clearer."
        )

    if intent == "metadata_missing":
        return (
            "- Use this format: Available fields; Missing fields; why unavailable; "
            "no estimation note."
        )

    if intent == "insight_summary":
        return (
            "- Summarize Creator Insight Score, Hook Analysis, Confirmed Public "
            "Metrics, Metadata Confidence, and recommendations."
        )

    return "- Prefer a clear structured answer when comparing Content 1 and Content 2."


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])

        return "".join(parts)

    return ""


def _direct_answer_tokens(answer: str) -> list[str]:
    lines = answer.splitlines()
    tokens: list[str] = []

    for index, line in enumerate(lines):
        suffix = "\n" if index < len(lines) - 1 else ""
        tokens.append(f"{line}{suffix}")

    return tokens or [answer]


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
