from typing import Any

from app.db.repositories.chat_repository import ChatRepository
from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.evidence_chunk_repository import EvidenceChunkRepository
from app.db.repositories.metadata_repository import MetadataRepository
from app.db.repositories.metric_source_repository import MetricSourceRepository
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.transcript_repository import TranscriptRepository
from app.db.session import database_session
from app.models.rag import RagChunk
from app.models.video import TranscriptSegment, VideoMetadata


def init_db() -> None:
    """Schema creation is owned by Alembic; retained for the V1 startup contract."""


def create_project_record(
    project_id: str,
    status: str,
    youtube_url: str | None = None,
    instagram_url: str | None = None,
    content_1_url: str | None = None,
    content_2_url: str | None = None,
    content_1_platform: str | None = None,
    content_2_platform: str | None = None,
) -> dict[str, Any]:
    first_url = content_1_url or youtube_url
    second_url = content_2_url or instagram_url
    if first_url is None or second_url is None:
        raise ValueError("Both content URLs are required.")
    with database_session() as session:
        return ProjectRepository(session).create(
            project_id=project_id,
            content_1_url=first_url,
            content_2_url=second_url,
            content_1_platform=content_1_platform or "youtube",
            content_2_platform=content_2_platform or "instagram",
            youtube_url=youtube_url,
            instagram_url=instagram_url,
            status=status,
        )


def update_project_status(project_id: str, status: str) -> None:
    with database_session() as session:
        ProjectRepository(session).update_status(project_id, status)


def get_project_record(project_id: str) -> dict[str, Any] | None:
    with database_session() as session:
        return ProjectRepository(session).get(project_id)


def list_project_records(limit: int = 20) -> list[dict[str, Any]]:
    with database_session() as session:
        return ProjectRepository(session).list(limit)


def upsert_video_metadata(
    project_id: str,
    metadata: VideoMetadata,
    slot: str | None = None,
) -> dict[str, Any]:
    content_slot = _content_slot(slot or metadata.slot or metadata.platform)
    with database_session() as session:
        content_repo = ContentItemRepository(session)
        metadata_repo = MetadataRepository(session)
        item = content_repo.upsert(
            project_id=project_id,
            slot=content_slot,
            platform=metadata.platform,
            url=metadata.url,
            extraction_status=metadata.extraction_status,
            transcript_available=metadata.transcript_available,
            transcript_segment_count=metadata.transcript_segment_count,
        )
        snapshot = metadata_repo.create_snapshot(
            content_item=item,
            metadata=metadata,
        )
        return metadata_repo.merge_record(content_repo.base_record(item), snapshot)


def get_video_by_project_platform(
    project_id: str, platform: str
) -> dict[str, Any] | None:
    with database_session() as session:
        content_repo = ContentItemRepository(session)
        metadata_repo = MetadataRepository(session)
        item = content_repo.get_model_by_platform(project_id, platform)
        if item is None:
            return None
        return metadata_repo.merge_record(
            content_repo.base_record(item), metadata_repo.latest_for_item(item.id)
        )


def get_video_by_project_slot(
    project_id: str, slot: str
) -> dict[str, Any] | None:
    with database_session() as session:
        content_repo = ContentItemRepository(session)
        metadata_repo = MetadataRepository(session)
        item = content_repo.get_model_by_slot(project_id, _content_slot(slot))
        if item is None:
            return None
        return metadata_repo.merge_record(
            content_repo.base_record(item), metadata_repo.latest_for_item(item.id)
        )


def list_video_records(project_id: str) -> list[dict[str, Any]]:
    with database_session() as session:
        content_repo = ContentItemRepository(session)
        metadata_repo = MetadataRepository(session)
        return [
            metadata_repo.merge_record(
                content_repo.base_record(item), metadata_repo.latest_for_item(item.id)
            )
            for item in content_repo.list_models(project_id)
        ]


def replace_transcript_segments(
    project_id: str,
    platform: str,
    video_id: str,
    segments: list[TranscriptSegment],
    slot: str | None = None,
) -> None:
    content_slot = _content_slot(slot or platform)
    with database_session() as session:
        TranscriptRepository(session).replace(
            project_id=project_id,
            content_item_id=video_id,
            slot=content_slot,
            platform=platform,
            segments=segments,
        )
        ContentItemRepository(session).update_transcript_state(
            video_id,
            available=bool(segments),
            count=len(segments),
        )


def get_transcript_preview(
    project_id: str,
    platform: str,
    limit: int = 10,
    slot: str | None = None,
) -> dict[str, Any] | None:
    if platform not in {"youtube", "instagram", "facebook"}:
        raise ValueError("Platform must be youtube, instagram, or facebook.")
    video = (
        get_video_by_project_slot(project_id, slot)
        if slot
        else get_video_by_project_platform(project_id, platform)
    )
    if video is None:
        return None
    with database_session() as session:
        records = TranscriptRepository(session).list(
            project_id=project_id,
            slot=str(video["slot"]),
            limit=limit,
        )
    return {
        "project_id": project_id,
        "slot": video["slot"],
        "platform": video["platform"],
        "transcript_available": video["transcript_available"],
        "transcript_segment_count": video["transcript_segment_count"],
        "transcript_language": video["transcript_language"],
        "detected_language": video["detected_language"],
        "language_confidence": video["language_confidence"],
        "transcript_source": video["transcript_source"],
        "transcript_source_note": video["transcript_source_note"],
        "segments": [
            TranscriptSegment(
                segment_index=record["segment_index"],
                start_time=record["start_time"],
                end_time=record["end_time"],
                text=record["text"],
            )
            for record in records
        ],
    }


def get_transcript_segments(
    project_id: str,
    platform: str,
    slot: str | None = None,
) -> list[dict[str, Any]]:
    content_slot = slot
    if content_slot is None:
        video = get_video_by_project_platform(project_id, platform)
        content_slot = str(video["slot"]) if video else platform
    with database_session() as session:
        return TranscriptRepository(session).list(
            project_id=project_id,
            slot=_content_slot(content_slot),
        )


def replace_rag_chunks(project_id: str, chunks: list[RagChunk]) -> None:
    with database_session() as session:
        EvidenceChunkRepository(session).replace(project_id, chunks)


def get_rag_chunks(
    project_id: str, platform: str | None = None
) -> list[dict[str, Any]]:
    if platform is not None and platform not in {"youtube", "instagram", "facebook"}:
        raise ValueError("Platform must be youtube, instagram, or facebook.")
    with database_session() as session:
        return EvidenceChunkRepository(session).list(project_id, platform)


def update_rag_chunk_qdrant_point_id(
    chunk_id: str, qdrant_point_id: str
) -> None:
    with database_session() as session:
        EvidenceChunkRepository(session).update_qdrant_point_id(
            chunk_id, qdrant_point_id
        )


def create_chat_session(
    project_id: str, session_id: str | None = None
) -> dict[str, Any]:
    with database_session() as session:
        return ChatRepository(session).create_session(project_id, session_id)


def get_chat_session(
    project_id: str, session_id: str
) -> dict[str, Any] | None:
    with database_session() as session:
        return ChatRepository(session).get_session(project_id, session_id)


def save_chat_message(
    project_id: str, session_id: str, role: str, content: str
) -> dict[str, Any]:
    with database_session() as session:
        return ChatRepository(session).save_message(
            project_id, session_id, role, content
        )


def get_chat_messages(
    project_id: str, session_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    with database_session() as session:
        return ChatRepository(session).list_messages(project_id, session_id, limit)


def delete_chat_session(project_id: str, session_id: str) -> None:
    with database_session() as session:
        ChatRepository(session).delete_session(project_id, session_id)


def save_chat_citations(
    message_id: str,
    project_id: str,
    session_id: str,
    citations: list[dict[str, Any]],
) -> None:
    with database_session() as session:
        ChatRepository(session).save_citations(
            message_id=message_id,
            project_id=project_id,
            session_id=session_id,
            citations=citations,
        )


def upsert_metric_source_record(**kwargs: Any) -> dict[str, Any]:
    with database_session() as session:
        return MetricSourceRepository(session).upsert(**kwargs)


def get_metric_source_record(
    project_id: str, record_id: str
) -> dict[str, Any] | None:
    with database_session() as session:
        return MetricSourceRepository(session).get(project_id, record_id)


def list_metric_source_records(project_id: str) -> list[dict[str, Any]]:
    with database_session() as session:
        return MetricSourceRepository(session).list(project_id)


def get_latest_metric_source(
    project_id: str,
    source_platform: str,
    metric_scope: str,
    source_method: str | None = None,
) -> dict[str, Any] | None:
    with database_session() as session:
        model = MetricSourceRepository(session).latest(
            project_id=project_id,
            source_platform=source_platform,
            metric_scope=metric_scope,
            source_method=source_method,
        )
        return MetricSourceRepository.to_record(model) if model is not None else None


def delete_metric_source_record(project_id: str, record_id: str) -> None:
    with database_session() as session:
        MetricSourceRepository(session).delete(project_id, record_id)


def get_project_detail_record(project_id: str) -> dict[str, Any] | None:
    project = get_project_record(project_id)
    if project is None:
        return None
    content_items = list_video_records(project_id)
    project["content_items"] = content_items
    project["youtube"] = next(
        (item for item in content_items if item["platform"] == "youtube"), None
    )
    project["instagram"] = next(
        (item for item in content_items if item["platform"] == "instagram"), None
    )
    return project


def _content_slot(value: str) -> str:
    if value in {"content_1", "content_2"}:
        return value
    if value == "youtube":
        return "content_1"
    if value in {"instagram", "facebook"}:
        return "content_2"
    raise ValueError("Content slot must be content_1 or content_2.")
