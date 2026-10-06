from typing import Any
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.content_item import ContentItem
from app.db.models.metadata_snapshot import MetadataSnapshot
from app.db.repositories._utils import utc_now
from app.models.video import VideoMetadata


class MetadataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_snapshot(
        self,
        *,
        content_item: ContentItem,
        metadata: VideoMetadata,
    ) -> MetadataSnapshot:
        captured_at = utc_now()
        previous_snapshot = self.latest_for_item(content_item.id)

        if previous_snapshot is not None:
            previous_captured_at = previous_snapshot.captured_at
            if previous_captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=None)
            if captured_at <= previous_captured_at:
                captured_at = previous_captured_at + timedelta(microseconds=1)

        snapshot = MetadataSnapshot(
            id=str(uuid4()),
            content_item_id=content_item.id,
            project_id=content_item.project_id,
            title=metadata.title,
            description=metadata.description,
            caption=metadata.caption,
            creator=metadata.creator,
            creator_handle=metadata.creator_handle,
            follower_count=metadata.follower_count,
            subscriber_count=metadata.subscriber_count,
            views=metadata.views,
            likes=metadata.likes,
            comments=metadata.comments,
            reactions=metadata.reactions,
            shares=metadata.shares,
            hashtags=list(metadata.hashtags),
            upload_date=metadata.upload_date,
            duration_seconds=metadata.duration_seconds,
            thumbnail_url=metadata.thumbnail_url,
            media_url=metadata.media_url,
            audio_url=metadata.audio_url,
            engagement_rate=metadata.engagement_rate,
            missing_fields=list(metadata.missing_fields),
            transcript_language=metadata.transcript_language,
            detected_language=metadata.detected_language,
            language_confidence=metadata.language_confidence,
            transcript_source=metadata.transcript_source,
            error_message=metadata.error_message,
            metric_source_note=metadata.metric_source_note,
            transcript_source_note=metadata.transcript_source_note,
            raw_payload=metadata.model_dump(mode="json"),
            captured_at=captured_at,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def latest_for_item(self, content_item_id: str) -> MetadataSnapshot | None:
        return self.session.scalar(
            select(MetadataSnapshot)
            .where(MetadataSnapshot.content_item_id == content_item_id)
            .order_by(desc(MetadataSnapshot.captured_at), desc(MetadataSnapshot.id))
            .limit(1)
        )

    @staticmethod
    def merge_record(
        base_record: dict[str, Any], snapshot: MetadataSnapshot | None
    ) -> dict[str, Any]:
        empty_values = {
            "title": None, "description": None, "caption": None,
            "creator": None, "creator_handle": None, "follower_count": None,
            "subscriber_count": None, "views": None, "likes": None,
            "comments": None, "reactions": None, "shares": None,
            "hashtags": [], "upload_date": None, "duration_seconds": None,
            "thumbnail_url": None, "media_url": None, "audio_url": None,
            "engagement_rate": None, "missing_fields": [],
            "transcript_language": None, "detected_language": None,
            "language_confidence": None, "transcript_source": None,
            "error_message": None, "metric_source_note": None,
            "transcript_source_note": None,
        }
        if snapshot is None:
            return {**base_record, **empty_values}

        return {
            **base_record,
            "title": snapshot.title,
            "description": snapshot.description,
            "caption": snapshot.caption,
            "creator": snapshot.creator,
            "creator_handle": snapshot.creator_handle,
            "follower_count": snapshot.follower_count,
            "subscriber_count": snapshot.subscriber_count,
            "views": snapshot.views,
            "likes": snapshot.likes,
            "comments": snapshot.comments,
            "reactions": snapshot.reactions,
            "shares": snapshot.shares,
            "hashtags": list(snapshot.hashtags or []),
            "upload_date": snapshot.upload_date,
            "duration_seconds": snapshot.duration_seconds,
            "thumbnail_url": snapshot.thumbnail_url,
            "media_url": snapshot.media_url,
            "audio_url": snapshot.audio_url,
            "engagement_rate": snapshot.engagement_rate,
            "missing_fields": list(snapshot.missing_fields or []),
            "transcript_language": snapshot.transcript_language,
            "detected_language": snapshot.detected_language,
            "language_confidence": snapshot.language_confidence,
            "transcript_source": snapshot.transcript_source,
            "error_message": snapshot.error_message,
            "metric_source_note": snapshot.metric_source_note,
            "transcript_source_note": snapshot.transcript_source_note,
        }
