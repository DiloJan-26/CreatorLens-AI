from sqlalchemy.orm import Session

from app.db.repositories.metric_source_repository import MetricSourceRepository
from tests.unit.test_content_item_repository import _create_project


def test_metric_source_repository_preserves_existing_v1_metrics(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    repository = MetricSourceRepository(db_session)

    created = repository.upsert(
        project_id=project_id,
        platform="youtube",
        source_platform="youtube",
        source_method="public_extractor",
        metric_scope="native",
        views=100,
        confidence="medium",
    )
    updated = repository.upsert(
        project_id=project_id,
        platform="youtube",
        source_platform="youtube",
        source_method="public_extractor",
        metric_scope="native",
        views=200,
        confidence="medium",
    )

    assert updated["id"] == created["id"]
    assert repository.list(project_id)[0]["views"] == 200
