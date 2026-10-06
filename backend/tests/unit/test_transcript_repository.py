from sqlalchemy.orm import Session

from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.transcript_repository import TranscriptRepository
from app.models.video import TranscriptSegment
from tests.unit.test_content_item_repository import _create_project


def test_transcript_repository_replaces_segments(db_session: Session) -> None:
    project_id = _create_project(db_session)
    content_repo = ContentItemRepository(db_session)
    item = content_repo.upsert(
        project_id=project_id,
        slot="content_1",
        platform="youtube",
        url="https://youtube.com/shorts/one",
        extraction_status="ready",
        transcript_available=True,
        transcript_segment_count=2,
    )
    repository = TranscriptRepository(db_session)
    repository.replace(
        project_id=project_id,
        content_item_id=item.id,
        slot="content_1",
        platform="youtube",
        segments=[
            TranscriptSegment(segment_index=0, start_time=0, end_time=1, text="A"),
            TranscriptSegment(segment_index=1, start_time=1, end_time=2, text="B"),
        ],
    )
    repository.replace(
        project_id=project_id,
        content_item_id=item.id,
        slot="content_1",
        platform="youtube",
        segments=[
            TranscriptSegment(segment_index=0, start_time=0, end_time=2, text="Updated")
        ],
    )

    records = repository.list(project_id=project_id, slot="content_1")
    assert [record["text"] for record in records] == ["Updated"]
    assert records[0]["video_id"] == item.id
