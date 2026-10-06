from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.evidence_chunk_repository import EvidenceChunkRepository
from app.models.rag import RagChunk
from tests.unit.test_content_item_repository import _create_project


def test_evidence_chunk_repository_replaces_and_updates_chunks(
    db_session: Session,
) -> None:
    project_id = _create_project(db_session)
    item = ContentItemRepository(db_session).upsert(
        project_id=project_id,
        slot="content_1",
        platform="youtube",
        url="https://youtube.com/shorts/one",
        extraction_status="ready",
        transcript_available=True,
        transcript_segment_count=1,
    )
    repository = EvidenceChunkRepository(db_session)
    chunk_id = str(uuid4())
    chunk = RagChunk(
        chunk_id=chunk_id,
        project_id=project_id,
        content_id=item.id,
        slot="content_1",
        platform="youtube",
        source_type="transcript",
        chunk_index=0,
        text="Evidence",
        content_hash="a" * 64,
        citation_label="Content 1 · YouTube · Transcript",
    )

    repository.replace(project_id, [chunk])
    records = repository.list(project_id)
    assert len(records) == 1
    assert records[0]["chunk_id"] == chunk_id

    point_id = str(uuid4())
    assert repository.update_qdrant_point_id(chunk_id, point_id) is True
    assert repository.list(project_id)[0]["qdrant_point_id"] == point_id
