import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.models.chat import ChatMessage, ChatStreamRequest, Citation
from app.rag.query_router import parse_target_reference_slots
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
            "You are CreatorLens AI, a senior short-form content strategist and RAG assistant.",
            "You combine general creator marketing reasoning with specialist evidence from the provided content sources.",
            "The compared items are always called Content 1 and Content 2. Never use Video A, Video B, or any other label.",
            "Always include the platform name: YouTube, Instagram, or Facebook.",
            "Use confirmed public metrics only. Say Unavailable when public data is missing.",
            "Do not invent views, likes, comments, reactions, shares, follower counts, subscriber counts, engagement rates, dates, duration, or transcript details.",
            "Distinguish confirmed metric performance from heuristic content-quality signals such as Hook Analysis and Creator Insight Score.",
            "Creator Insight Scores are heuristic review signals, not guaranteed performance predictions.",
            "Metadata Availability supports confidence only; it is not a performance score or creator quality score.",
            "If metric data is incomplete, say the comparison is limited.",
            "For strategy, performance, hook, improvement, and rewrite questions, always give enough reasoning for a creator or marketer to take action.",
            "Never give one-line or one-paragraph answers for strategy, improvement, hook, or rewrite questions.",
            "Use clear numbered sections with diagnosis, evidence, specific changes, and next steps.",
            "If the user asks for N improvement points, return exactly N numbered points — no more, no fewer.",
            "Each improvement point must include: the issue, the evidence from retrieved sources, the specific change to make, and why that change should help.",
            "For improvement questions, identify what the target content currently does, what the reference content does better, and provide concrete actionable points.",
            "For rewrite questions, provide diagnosis of what is weak, a rewritten opening, why it is stronger, and an optional alternative version.",
            "For hook questions, identify hook type for both contents, which opening is stronger and exactly why, a specific improvement, and an example rewritten hook.",
            "For performance reasoning, compare confirmed metrics first, then hook, caption, CTA, and audience angle differences.",
            "Complete every answer fully before the citations are shown. Do not stop mid-sentence or mid-section.",
            "Use citations only from backend-provided source labels. Do not fabricate citation labels.",
            "The frontend displays citations separately; do not reproduce source labels inside the answer text.",
            "If evidence is limited, state exactly what is missing and what you are basing your answer on.",
            "Never claim Instagram underperformed solely from missing views.",
            "If Facebook cross-post data is not connected, say combined Meta performance may be incomplete.",
            "Treat the structured Content 1 and Content 2 metadata as the source of truth for confirmed public metrics.",
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
        target_slot, reference_slot = parse_target_reference_slots(question)
        messages = [
            SystemMessage(content=build_system_prompt()),
            HumanMessage(
                content=_human_prompt(
                    question=question,
                    intent=rag_context.intent,
                    structured_context=rag_context.structured_context,
                    retrieved_context=rag_context.retrieved_context,
                    history_text=history_text,
                    target_slot=target_slot,
                    reference_slot=reference_slot,
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
    target_slot: str | None = None,
    reference_slot: str | None = None,
) -> str:
    source_context = retrieved_context.strip() or "No retrieved source chunks were needed for this question."
    style_instructions = _answer_style_instructions(intent, target_slot, reference_slot)

    target_line = ""
    if target_slot or reference_slot:
        target_label = "Content 1" if target_slot == "content_1" else ("Content 2" if target_slot == "content_2" else "")
        reference_label = "Content 2" if reference_slot == "content_2" else ("Content 1" if reference_slot == "content_1" else "")
        if target_label and reference_label:
            target_line = f"\nImprovement direction: Improve {target_label} using insights from {reference_label}.\n"
        elif target_label:
            target_line = f"\nTarget content: {target_label}.\n"

    return "\n\n".join(
        [
            f"User question:\n{question}",
            f"Question intent:\n{intent}{target_line}",
            f"Recent conversation:\n{history_text}",
            f"Structured metadata context:\n{structured_context}",
            f"Retrieved source context:\n{source_context}",
            "Answer requirements:\n"
            "- Ground every claim in the provided context.\n"
            "- Say Unavailable when public data is missing.\n"
            "- Name Content 1 and Content 2 with their platform names.\n"
            "- Separate confirmed public metrics from heuristic insight scores.\n"
            "- Treat Metadata Availability as confidence context, not as a quality or performance score.\n"
            "- Do not output fake citation labels.\n"
            "- For reasoning, improvement, hook, or rewrite questions: use structured numbered sections. "
            "Do not give a single-paragraph answer.\n"
            "- If the user asks for a specific number of points, return exactly that many numbered points.\n"
            "- Complete the full answer before stopping. Do not truncate mid-section.\n"
            f"{style_instructions}",
        ]
    )


def _answer_style_instructions(
    intent: str,
    target_slot: str | None = None,
    reference_slot: str | None = None,
) -> str:
    target_label = (
        "Content 1" if target_slot == "content_1"
        else "Content 2" if target_slot == "content_2"
        else "the target content"
    )
    reference_label = (
        "Content 2" if reference_slot == "content_2"
        else "Content 1" if reference_slot == "content_1"
        else "the reference content"
    )

    if intent == "performance_reasoning":
        return (
            "- Use this format:\n"
            "1. Quick verdict (1–2 sentences)\n"
            "2. Confirmed public metrics comparison (cite exact numbers or say Unavailable)\n"
            "3. Hook and first-seconds analysis for both contents\n"
            "4. Caption/description/CTA analysis for both contents\n"
            "5. Audience and content angle difference\n"
            "6. Metadata limitations\n"
            "7. Actionable next step for the creator"
        )

    if intent == "hook_analysis":
        return (
            "- Use this format:\n"
            "1. Content 1 hook type, first-second clarity, and evidence (quote from retrieved chunks if available)\n"
            "2. Content 2 hook type, first-second clarity, and evidence\n"
            "3. Which opening is stronger and the exact reason why\n"
            "4. Specific thing to fix in the weaker hook\n"
            "5. Example rewritten hook for the weaker content"
        )

    if intent == "improvement_suggestions":
        return (
            f"- The user wants to improve {target_label} using insights from {reference_label}.\n"
            "- If the user asked for a specific number of improvement points, return exactly that many numbered points.\n"
            "- Use this format:\n"
            f"1. Quick verdict (one sentence comparing {target_label} and {reference_label})\n"
            f"2. What {target_label} currently does (hook type, caption style, CTA, content angle)\n"
            f"3. What {reference_label} does better or differently\n"
            "4. Improvement points (exactly the number the user requested — each must include):\n"
            "   - Issue: the specific weakness\n"
            "   - Evidence: quote or reference from retrieved source chunks\n"
            "   - Change: the specific thing to do differently\n"
            "   - Why: why this change should improve engagement or clarity\n"
            "5. Optional example rewrite of the hook or caption opening\n"
            "6. Evidence limitation note if key transcript/caption data was unavailable"
        )

    if intent == "rewrite_request":
        return (
            "- Use this format:\n"
            "1. Diagnosis (what is weak or generic about the current opening or caption)\n"
            "2. Rewritten opening or caption (make it specific, hook-driven, and strong)\n"
            "3. Why this rewrite is stronger (cite hook type, clarity improvement, CTA)\n"
            "4. Optional alternative version\n"
            "5. What source evidence or pattern inspired the rewrite"
        )

    if intent == "metadata_missing":
        return (
            "- Use this format: Available fields for each content; Missing fields for each content; "
            "why they are likely unavailable; confirmation that no missing values were estimated."
        )

    if intent == "insight_summary":
        return (
            "- Summarize in sections:\n"
            "1. Content 1 Creator Insight Score, Hook Analysis, and top strengths\n"
            "2. Content 2 Creator Insight Score, Hook Analysis, and top strengths\n"
            "3. Comparison: confirmed metric winner, hook winner, overall insight winner\n"
            "4. Top recommendations\n"
            "5. Metadata confidence note"
        )

    return (
        "- Use a clear structured answer when comparing Content 1 and Content 2.\n"
        "- Include: diagnosis, evidence from retrieved chunks, specific recommendations, and next steps."
    )


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
