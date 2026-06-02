import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.chat import ChatMessage, ChatStreamRequest, Citation
from app.rag.context_builder import (
    RagContextProjectNotFoundError,
    RagContextValidationError,
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
            "Answer using only structured metadata and retrieved source context.",
            "Do not invent views, likes, comments, follower counts, engagement rates, dates, or transcript details.",
            "If a value is unavailable, say it is unavailable.",
            "For Instagram, mention public extraction limitations or Facebook cross-post caveats when relevant.",
            "Prefer concise, creator-focused, actionable answers.",
            "Use YouTube and Instagram names exactly.",
            "Do not mention internal implementation labels or development phases.",
            "Do not fabricate citations.",
            "The frontend will display citations separately, so do not create fake source labels.",
            "If useful, refer to sources naturally, but citations are provided separately.",
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
        rag_context = build_rag_context(project_id=project_id, message=question)
        citations = rag_context.citations
        llm = get_llm(streaming=True)
        messages = [
            SystemMessage(content=build_system_prompt()),
            HumanMessage(
                content=_human_prompt(
                    question=question,
                    intent=rag_context.intent,
                    structured_context=rag_context.structured_context,
                    retrieved_context=rag_context.retrieved_context,
                    history_text=format_chat_history(recent_messages),
                )
            ),
        ]

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


def _human_prompt(
    question: str,
    intent: str,
    structured_context: str,
    retrieved_context: str,
    history_text: str,
) -> str:
    source_context = retrieved_context.strip() or "No retrieved source chunks were needed for this question."

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
            "- Keep the answer concise and useful for creator analysis.\n"
            "- Do not output fake citation labels.",
        ]
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


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
