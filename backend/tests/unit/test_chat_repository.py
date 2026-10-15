from sqlalchemy.orm import Session

from app.db.repositories.chat_repository import ChatRepository
from tests.unit.test_content_item_repository import _create_project


def test_chat_repository_persists_session_messages_and_citations(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    repository = ChatRepository(db_session)
    chat_session = repository.create_session(project_id)
    message = repository.save_message(
        project_id,
        chat_session["session_id"],
        "assistant",
        "Grounded answer",
    )
    repository.save_citations(
        message_id=message["message_id"],
        project_id=project_id,
        session_id=chat_session["session_id"],
        citations=[
            {
                "platform": "youtube",
                "source_type": "transcript",
                "citation_label": "Content 1 · YouTube · Transcript",
                "text": "Evidence",
                "score": 0.9,
            }
        ],
    )

    messages = repository.list_messages(project_id, chat_session["session_id"])
    assert [record["content"] for record in messages] == ["Grounded answer"]

    repository.delete_session(project_id, chat_session["session_id"])
    assert repository.get_session(project_id, chat_session["session_id"]) is None
