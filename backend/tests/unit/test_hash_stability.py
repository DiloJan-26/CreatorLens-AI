from datetime import datetime, timedelta, timezone

from app.services.hash_service import (
    hash_chunk,
    hash_content,
    hash_embedding,
    hash_metadata,
    hash_payload,
    hash_transcript,
)


def test_mapping_order_does_not_change_hash() -> None:
    first = {"title": "Launch", "metrics": {"views": 10, "likes": 2}}
    second = {"metrics": {"likes": 2, "views": 10}, "title": "Launch"}

    assert hash_metadata(first) == hash_metadata(second)


def test_equivalent_aware_datetimes_have_the_same_hash() -> None:
    utc_value = datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc)
    sri_lanka_value = utc_value.astimezone(timezone(timedelta(hours=5, minutes=30)))

    assert hash_payload({"captured_at": utc_value}) == hash_payload(
        {"captured_at": sri_lanka_value}
    )


def test_content_and_embedding_hashes_include_compatibility_inputs() -> None:
    transcript_hash = hash_transcript([{"index": 0, "text": "Evidence"}])
    metadata_hash = hash_metadata({"title": "Example"})
    content_hash = hash_content(
        metadata_hash=metadata_hash,
        transcript_hash=transcript_hash,
    )
    chunk_hash = hash_chunk("Evidence")

    assert len(content_hash) == 64
    assert hash_embedding(
        chunk_hash=chunk_hash,
        model_name="BAAI/bge-small-en-v1.5",
        model_version="1",
    ) != hash_embedding(
        chunk_hash=chunk_hash,
        model_name="BAAI/bge-small-en-v1.5",
        model_version="2",
    )
