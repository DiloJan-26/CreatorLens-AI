from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.metadata_repository import MetadataRepository
from app.models.video import VideoMetadata
from tests.unit.test_content_item_repository import _create_project


def test_metadata_repository_returns_latest_snapshot(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_time = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "app.db.repositories.metadata_repository.utc_now",
        lambda: fixed_time,
    )
    project_id = _create_project(db_session)
    content_repo = ContentItemRepository(db_session)
    repository = MetadataRepository(db_session)
    item = content_repo.upsert(
        project_id=project_id,
        slot="content_1",
        platform="youtube",
        url="https://youtube.com/shorts/one",
        extraction_status="ready",
        transcript_available=False,
        transcript_segment_count=0,
    )

    repository.create_snapshot(
        content_item=item,
        metadata=VideoMetadata(
            slot="content_1",
            platform="youtube",
            url=item.url,
            title="First title",
            views=10,
        ),
    )
    latest = repository.create_snapshot(
        content_item=item,
        metadata=VideoMetadata(
            slot="content_1",
            platform="youtube",
            url=item.url,
            title="Updated title",
            views=20,
        ),
    )

    loaded = repository.latest_for_item(item.id)
    assert loaded is not None
    assert loaded.id == latest.id
    record = repository.merge_record(content_repo.base_record(item), loaded)
    assert record["title"] == "Updated title"
    assert record["views"] == 20
