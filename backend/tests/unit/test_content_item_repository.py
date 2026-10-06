from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.project_repository import ProjectRepository


def test_content_item_repository_upserts_by_project_and_slot(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    repository = ContentItemRepository(db_session)

    first = repository.upsert(
        project_id=project_id,
        slot="content_1",
        platform="youtube",
        url="https://youtube.com/shorts/one",
        extraction_status="pending",
        transcript_available=False,
        transcript_segment_count=0,
    )
    updated = repository.upsert(
        project_id=project_id,
        slot="content_1",
        platform="youtube",
        url="https://youtube.com/shorts/one",
        extraction_status="ready",
        transcript_available=True,
        transcript_segment_count=2,
    )

    assert updated.id == first.id
    assert updated.extraction_status == "ready"
    assert len(repository.list_models(project_id)) == 1


def _create_project(session: Session) -> str:
    project_id = str(uuid4())
    ProjectRepository(session).create(
        project_id=project_id,
        content_1_url="https://youtube.com/shorts/one",
        content_2_url="https://instagram.com/reel/two",
        content_1_platform="youtube",
        content_2_platform="instagram",
        status="created",
    )
    return project_id
