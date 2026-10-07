from app.schemas.ingestion import IngestionJobStatus
from app.workers.indexing_tasks import completion_status_for_content


def test_two_complete_transcripts_are_ready() -> None:
    records = [
        {"extraction_status": "ready", "transcript_available": True},
        {"extraction_status": "ready", "transcript_available": True},
    ]

    assert completion_status_for_content(records) == IngestionJobStatus.READY


def test_missing_transcript_is_partial_ready() -> None:
    records = [
        {"extraction_status": "ready", "transcript_available": True},
        {"extraction_status": "partial", "transcript_available": False},
    ]

    assert (
        completion_status_for_content(records)
        == IngestionJobStatus.PARTIAL_READY
    )


def test_metadata_only_content_is_partial_ready() -> None:
    records = [
        {"extraction_status": "partial", "transcript_available": False},
    ]

    assert (
        completion_status_for_content(records)
        == IngestionJobStatus.PARTIAL_READY
    )


def test_no_usable_content_is_failed() -> None:
    records = [
        {"extraction_status": "failed", "transcript_available": False},
    ]

    assert completion_status_for_content(records) == IngestionJobStatus.FAILED

