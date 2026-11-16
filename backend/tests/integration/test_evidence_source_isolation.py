from contextlib import contextmanager
from app.db.repositories import storage_repository as storage
from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.metric_source_repository import MetricSourceRepository
from app.db.repositories.metadata_repository import MetadataRepository
from app.models.video import VideoMetadata
from app.services import metric_source_service as metrics
from tests.unit.test_content_item_repository import _create_project


def test_same_platform_sources_stay_separate_and_legacy_is_not_copied(db_session, monkeypatch):
    project_id = _create_project(db_session)
    for slot, views in [("content_1", 34021), ("content_2", 1527222)]:
        item = ContentItemRepository(db_session).upsert(project_id=project_id, slot=slot,
            platform="youtube", url=f"https://youtu.be/{slot}", extraction_status="partial",
            transcript_available=False, transcript_segment_count=0)
        MetadataRepository(db_session).create_snapshot(content_item=item, metadata=VideoMetadata(
            slot=slot, platform="youtube", url=item.url, views=views))
    repo = MetricSourceRepository(db_session)
    legacy = repo.upsert(project_id=project_id, platform="youtube", source_platform="youtube",
        source_method="public_extractor", metric_scope="native", views=99)

    @contextmanager
    def session():
        yield db_session
    monkeypatch.setattr(storage, "database_session", session)
    for name in ("get_project_record", "list_video_records", "upsert_metric_source_record", "list_metric_source_records"):
        monkeypatch.setattr(metrics, name, getattr(storage, name))
    summary = metrics.get_metric_summary(project_id)
    bound = {row.slot: row for row in summary.records if row.slot}
    assert bound["content_1"].views == 34021
    assert bound["content_2"].views == 1527222
    assert bound["content_1"].content_item_id != bound["content_2"].content_item_id
    assert repo.get(project_id, legacy["id"])["views"] == 99
    assert repo.get(project_id, legacy["id"])["identity_status"] == "legacy_unresolved"
    assert summary.youtube_status == "unavailable"  # Platform scalar is ambiguous, not either content.
    metrics.ensure_public_metric_records(project_id)
    assert len(repo.list(project_id)) == 3


def test_transcript_write_rejects_foreign_slot(db_session):
    import pytest
    from app.db.repositories.transcript_repository import TranscriptRepository
    from app.models.video import TranscriptSegment
    project_id = _create_project(db_session)
    item = ContentItemRepository(db_session).upsert(project_id=project_id, slot="content_1", platform="youtube",
        url="https://youtu.be/synthetic", extraction_status="partial", transcript_available=False, transcript_segment_count=0)
    with pytest.raises(ValueError, match="identity"):
        TranscriptRepository(db_session).replace(project_id=project_id, content_item_id=item.id,
            slot="content_2", platform="youtube", segments=[TranscriptSegment(segment_index=0, text="wrong slot")])


def test_explicit_five_second_query_excludes_boundary_chunk(monkeypatch):
    from app.rag import retrieval_service
    from app.models.rag import RetrieveRequest
    from tests.integration.test_hybrid_retrieval_flow import _configure_retrieval_mocks
    _configure_retrieval_mocks(monkeypatch)
    response = retrieval_service.retrieve_project_chunks("project-1", RetrieveRequest(query="Compare hooks in the first 5 seconds"))
    assert response.results
    assert all(row.end_time <= 5 for row in response.results)
    assert response.evidence_limitations


def test_legacy_sqlite_keeps_slot_provenance_and_quality(monkeypatch):
    from pathlib import Path
    from app.services import storage_service as legacy
    import tempfile
    from contextlib import closing
    connect = legacy._connect
    @contextmanager
    def closed_connection():
        with closing(connect()) as connection, connection:
            yield connection
    monkeypatch.setattr(legacy, "_connect", closed_connection)
    # Keep disposable storage under audit cwd; never touch backend/storage.
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
        monkeypatch.setattr(legacy, "STORAGE_DIR", Path(folder))
        monkeypatch.setattr(legacy, "SQLITE_DB_PATH", Path(folder)/"test.db")
        project_id = "synthetic-legacy"
        legacy.create_project_record(project_id=project_id, status="created", content_1_url="https://youtu.be/one",
            content_2_url="https://youtu.be/two", content_1_platform="youtube", content_2_platform="youtube")
        for slot, views in [("content_1", 10), ("content_2", 20)]:
            metadata = VideoMetadata(slot=slot, platform="youtube", url=f"https://youtu.be/{slot}", views=views,
                                     transcript_evidence={"status": "partial", "revision": slot})
            record = legacy.upsert_video_metadata(project_id, metadata, slot=slot)
            assert record["transcript_evidence"]["revision"] == slot
            legacy.upsert_metric_source_record(project_id, "youtube", "youtube", "public_extractor", "native",
                slot=slot, content_item_id=record["id"], views=views)
        assert {r["slot"]: r["views"] for r in legacy.list_metric_source_records(project_id)} == {"content_1": 10, "content_2": 20}
