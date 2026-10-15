from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.repositories.project_repository import ProjectRepository


def test_project_repository_create_load_list_and_update(db_session: Session) -> None:
    repository = ProjectRepository(db_session)
    project_id = str(uuid4())

    created = repository.create(
        project_id=project_id,
        content_1_url="https://youtube.com/shorts/example",
        content_2_url="https://instagram.com/reel/example",
        content_1_platform="youtube",
        content_2_platform="instagram",
        youtube_url="https://youtube.com/shorts/example",
        instagram_url="https://instagram.com/reel/example",
        status="created",
    )

    assert created["project_id"] == project_id
    assert repository.get(project_id) == created
    assert repository.list() == [created]

    assert repository.update_status(project_id, "ready") is True
    assert repository.get(project_id)["status"] == "ready"  # type: ignore[index]
