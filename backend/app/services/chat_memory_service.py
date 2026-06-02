from app.models.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatSession,
)
from app.services.storage_service import (
    create_chat_session,
    delete_chat_session,
    get_chat_messages,
    get_chat_session,
    get_project_record,
    save_chat_message,
)


class ChatProjectNotFoundError(Exception):
    """Raised when chat memory is requested for a missing project."""


class ChatSessionNotFoundError(Exception):
    """Raised when a chat session cannot be found."""


class ChatValidationError(Exception):
    """Raised when chat memory input is invalid."""


VALID_CHAT_ROLES = {"user", "assistant", "system"}


def create_or_get_session(
    project_id: str,
    session_id: str | None = None,
) -> ChatSession:
    _ensure_project_exists(project_id)

    if session_id is not None and not session_id.strip():
        raise ChatValidationError("Session ID must not be empty.")

    if session_id:
        existing_session = get_chat_session(project_id=project_id, session_id=session_id)

        if existing_session is not None:
            return ChatSession(**existing_session)

    return ChatSession(
        **create_chat_session(project_id=project_id, session_id=session_id)
    )


def add_message(
    project_id: str,
    session_id: str,
    role: str,
    content: str,
) -> ChatMessage:
    _ensure_project_exists(project_id)
    _ensure_session_exists(project_id=project_id, session_id=session_id)

    clean_role = role.strip().lower()
    if clean_role not in VALID_CHAT_ROLES:
        raise ChatValidationError("Role must be user, assistant, or system.")

    clean_content = content.strip()
    if not clean_content:
        raise ChatValidationError("Message content must not be empty.")

    return ChatMessage(
        **save_chat_message(
            project_id=project_id,
            session_id=session_id,
            role=clean_role,
            content=clean_content,
        )
    )


def get_recent_messages(
    project_id: str,
    session_id: str,
    limit: int = 10,
) -> list[ChatMessage]:
    _ensure_project_exists(project_id)
    _ensure_session_exists(project_id=project_id, session_id=session_id)

    return [
        ChatMessage(**record)
        for record in get_chat_messages(
            project_id=project_id,
            session_id=session_id,
            limit=limit,
        )
    ]


def get_chat_history(project_id: str, session_id: str) -> ChatHistoryResponse:
    messages = get_recent_messages(
        project_id=project_id,
        session_id=session_id,
        limit=100,
    )

    return ChatHistoryResponse(
        project_id=project_id,
        session_id=session_id,
        messages=messages,
    )


def clear_chat_session(project_id: str, session_id: str) -> None:
    _ensure_project_exists(project_id)
    _ensure_session_exists(project_id=project_id, session_id=session_id)
    delete_chat_session(project_id=project_id, session_id=session_id)


def _ensure_project_exists(project_id: str) -> None:
    if get_project_record(project_id) is None:
        raise ChatProjectNotFoundError("Project not found.")


def _ensure_session_exists(project_id: str, session_id: str) -> ChatSession:
    session = get_chat_session(project_id=project_id, session_id=session_id)

    if session is None:
        raise ChatSessionNotFoundError("Chat session not found.")

    return ChatSession(**session)

