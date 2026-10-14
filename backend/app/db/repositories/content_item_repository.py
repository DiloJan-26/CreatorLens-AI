from typing import Any
from uuid import uuid4

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.db.models.content_item import ContentItem
from app.db.repositories._utils import iso_timestamp, utc_now


SLOT_ORDER = case(
    (ContentItem.slot == "content_1", 0),
    (ContentItem.slot == "content_2", 1),
    else_=2,
)


class ContentItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        project_id: str,
        slot: str,
        platform: str,
        url: str,
        extraction_status: str,
        transcript_available: bool,
        transcript_segment_count: int,
        normalized_url: str | None = None,
    ) -> ContentItem:
        item = self.get_model_by_slot(project_id, slot)
        timestamp = utc_now()
        if item is None:
            item = ContentItem(
                id=str(uuid4()),
                project_id=project_id,
                slot=slot,
                platform=platform,
                url=url,
                normalized_url=normalized_url,
                extraction_status=extraction_status,
                transcript_available=transcript_available,
                transcript_segment_count=transcript_segment_count,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(item)
        else:
            item.platform = platform
            item.url = url
            item.normalized_url = normalized_url
            item.content_hash = None
            item.metadata_hash = None
            item.transcript_hash = None
            item.extraction_status = extraction_status
            item.transcript_available = transcript_available
            item.transcript_segment_count = transcript_segment_count
            item.updated_at = timestamp
        self.session.flush()
        return item

    def find_reusable_by_normalized_url(
        self, normalized_url: str
    ) -> ContentItem | None:
        return self.session.scalar(
            select(ContentItem)
            .where(
                ContentItem.normalized_url == normalized_url,
                ContentItem.extraction_status == "ready",
                ContentItem.transcript_available.is_(True),
                ContentItem.content_hash.is_not(None),
                ContentItem.metadata_hash.is_not(None),
                ContentItem.transcript_hash.is_not(None),
            )
            .order_by(ContentItem.updated_at.desc())
            .limit(1)
        )

    def set_cache_identity(
        self,
        content_item_id: str,
        *,
        content_hash: str,
        metadata_hash: str,
        transcript_hash: str,
    ) -> None:
        item = self.session.get(ContentItem, content_item_id)
        if item is None:
            raise LookupError("Content item not found.")
        item.content_hash = content_hash
        item.metadata_hash = metadata_hash
        item.transcript_hash = transcript_hash
        item.updated_at = utc_now()
        self.session.flush()

    def get_model_by_slot(self, project_id: str, slot: str) -> ContentItem | None:
        return self.session.scalar(
            select(ContentItem).where(
                ContentItem.project_id == project_id,
                ContentItem.slot == slot,
            )
        )

    def get_model_by_platform(
        self, project_id: str, platform: str
    ) -> ContentItem | None:
        return self.session.scalar(
            select(ContentItem)
            .where(
                ContentItem.project_id == project_id,
                ContentItem.platform == platform,
            )
            .order_by(SLOT_ORDER)
            .limit(1)
        )

    def list_models(self, project_id: str) -> list[ContentItem]:
        return list(
            self.session.scalars(
                select(ContentItem)
                .where(ContentItem.project_id == project_id)
                .order_by(SLOT_ORDER, ContentItem.created_at)
            ).all()
        )

    def update_transcript_state(
        self, content_item_id: str, *, available: bool, count: int
    ) -> None:
        item = self.session.get(ContentItem, content_item_id)
        if item is None:
            raise LookupError("Content item not found.")
        item.transcript_available = available
        item.transcript_segment_count = count
        item.updated_at = utc_now()
        self.session.flush()

    @staticmethod
    def base_record(item: ContentItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "slot": item.slot,
            "platform": item.platform,
            "url": item.url,
            "normalized_url": item.normalized_url,
            "content_hash": item.content_hash,
            "metadata_hash": item.metadata_hash,
            "transcript_hash": item.transcript_hash,
            "extraction_status": item.extraction_status,
            "transcript_available": item.transcript_available,
            "transcript_segment_count": item.transcript_segment_count,
            "created_at": iso_timestamp(item.created_at),
            "updated_at": iso_timestamp(item.updated_at),
        }
