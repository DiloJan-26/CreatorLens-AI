from typing import Any
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.db.models.chat import ChatCitation, ChatMessage, ChatSession
from app.db.repositories._utils import iso_timestamp, utc_now


class ChatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_session(
        self, project_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        identifier = (session_id or "").strip() or str(uuid4())
        timestamp = utc_now()
        model = ChatSession(
            id=identifier,
            project_id=project_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(model)
        self.session.flush()
        return self.session_record(model)

    def get_session(
        self, project_id: str, session_id: str
    ) -> dict[str, Any] | None:
        model = self.session.scalar(
            select(ChatSession).where(
                ChatSession.project_id == project_id,
                ChatSession.id == session_id,
            )
        )
        return self.session_record(model) if model is not None else None

    def save_message(
        self, project_id: str, session_id: str, role: str, content: str
    ) -> dict[str, Any]:
        timestamp = utc_now()
        message = ChatMessage(
            id=str(uuid4()),
            session_id=session_id,
            project_id=project_id,
            role=role,
            content=content,
            created_at=timestamp,
        )
        self.session.add(message)
        chat_session = self.session.get(ChatSession, session_id)
        if chat_session is not None and chat_session.project_id == project_id:
            chat_session.updated_at = timestamp
        self.session.flush()
        return self.message_record(message)

    def list_messages(
        self, project_id: str, session_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        messages = list(
            self.session.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.project_id == project_id,
                    ChatMessage.session_id == session_id,
                )
                .order_by(desc(ChatMessage.created_at))
                .limit(safe_limit)
            ).all()
        )
        messages.reverse()
        return [self.message_record(message) for message in messages]

    def delete_session(self, project_id: str, session_id: str) -> None:
        self.session.execute(
            delete(ChatSession).where(
                ChatSession.project_id == project_id,
                ChatSession.id == session_id,
            )
        )
        self.session.flush()

    def save_citations(
        self,
        *,
        message_id: str,
        project_id: str,
        session_id: str,
        citations: list[dict[str, Any]],
    ) -> None:
        timestamp = utc_now()
        self.session.add_all(
            [
                ChatCitation(
                    id=str(uuid4()),
                    message_id=message_id,
                    session_id=session_id,
                    project_id=project_id,
                    platform=_optional_text(citation.get("platform")),
                    source_type=_optional_text(citation.get("source_type")),
                    citation_label=_optional_text(citation.get("citation_label")),
                    text=_optional_text(citation.get("text")),
                    score=_optional_float(citation.get("score")),
                    created_at=timestamp,
                )
                for citation in citations
            ]
        )
        self.session.flush()

    @staticmethod
    def session_record(model: ChatSession) -> dict[str, Any]:
        return {
            "session_id": model.id,
            "project_id": model.project_id,
            "created_at": iso_timestamp(model.created_at),
            "updated_at": iso_timestamp(model.updated_at),
        }

    @staticmethod
    def message_record(model: ChatMessage) -> dict[str, Any]:
        return {
            "message_id": model.id,
            "session_id": model.session_id,
            "project_id": model.project_id,
            "role": model.role,
            "content": model.content,
            "created_at": iso_timestamp(model.created_at),
        }


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None
