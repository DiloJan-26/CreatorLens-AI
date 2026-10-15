from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models.chat import (
    ChatHistoryResponse,
    ChatRequest,
    ChatStreamRequest,
    CreateChatSessionResponse,
    RagContext,
)
from app.rag.chat_service import stream_chat_answer
from app.rag.context_builder import (
    RagContextProjectNotFoundError,
    RagContextValidationError,
    build_rag_context,
)
from app.rag.retrieval_service import RetrievalValidationError
from app.services.qdrant_service import QdrantConfigurationError
from app.services.chat_memory_service import (
    ChatProjectNotFoundError,
    ChatSessionNotFoundError,
    ChatValidationError,
    clear_chat_session,
    create_or_get_session,
    get_chat_history,
    get_recent_messages,
)


router = APIRouter(prefix="/api/projects/{project_id}/chat")


class CreateChatSessionRequest(BaseModel):
    session_id: str | None = None


@router.post(
    "/sessions",
    response_model=CreateChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["8. Chat Sessions"],
    summary="1. Create or reuse a chat session",
    description="Creates a persisted session for this project before streaming chat.",
)
def create_chat_session_endpoint(
    project_id: str,
    payload: CreateChatSessionRequest | None = Body(default=None),
) -> CreateChatSessionResponse:
    try:
        session = create_or_get_session(
            project_id=project_id,
            session_id=payload.session_id if payload else None,
        )
    except ChatProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except ChatValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    return CreateChatSessionResponse(
        project_id=project_id,
        session_id=session.session_id,
        message="Chat session is ready.",
    )


@router.get(
    "/sessions/{session_id}",
    response_model=ChatHistoryResponse,
    tags=["8. Chat Sessions"],
    summary="Load chat history",
    description="Returns persisted messages for one project chat session.",
)
def get_chat_history_endpoint(
    project_id: str,
    session_id: str,
) -> ChatHistoryResponse:
    try:
        return get_chat_history(project_id=project_id, session_id=session_id)
    except (ChatProjectNotFoundError, ChatSessionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None


@router.delete(
    "/sessions/{session_id}",
    tags=["8. Chat Sessions"],
    summary="Delete a chat session",
    description="Deletes the selected session and its persisted messages and citations.",
)
def delete_chat_session_endpoint(project_id: str, session_id: str) -> dict[str, str]:
    try:
        clear_chat_session(project_id=project_id, session_id=session_id)
    except (ChatProjectNotFoundError, ChatSessionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None

    return {
        "status": "deleted",
        "session_id": session_id,
    }


@router.post(
    "/context-preview",
    response_model=RagContext,
    tags=["5. Retrieval & Context"],
    summary="8. Preview assembled RAG context",
    description=(
        "Combines retrieved evidence, deterministic insight context, and optional "
        "recent chat history without generating the final LLM answer."
    ),
)
def preview_chat_context_endpoint(
    project_id: str,
    payload: ChatRequest,
) -> RagContext:
    try:
        recent_messages = (
            get_recent_messages(
                project_id=project_id,
                session_id=payload.session_id,
                limit=10,
            )
            if payload.session_id
            else None
        )
        return build_rag_context(
            project_id=project_id,
            message=payload.message,
            recent_messages=recent_messages,
        )
    except RagContextProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        ) from None
    except (ChatProjectNotFoundError, ChatSessionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None
    except (RagContextValidationError, RetrievalValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    except QdrantConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant is not configured.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not build RAG context.",
        ) from None


@router.post(
    "/stream",
    tags=["9. AI Chat"],
    summary="2. Stream a cited AI answer",
    description=(
        "Streams trace, citation, token, completion, or error events using "
        "`text/event-stream`. Requires indexed evidence and a valid session."
    ),
)
def stream_chat_endpoint(
    project_id: str,
    payload: ChatStreamRequest,
) -> StreamingResponse:
    return StreamingResponse(
        stream_chat_answer(project_id=project_id, request=payload),
        media_type="text/event-stream",
    )
