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
            item.extraction_status = extraction_status
            item.transcript_available = transcript_available
            item.transcript_segment_count = transcript_segment_count
            item.updated_at = timestamp
        self.session.flush()
        return item

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
            "extraction_status": item.extraction_status,
            "transcript_available": item.transcript_available,
            "transcript_segment_count": item.transcript_segment_count,
            "created_at": iso_timestamp(item.created_at),
            "updated_at": iso_timestamp(item.updated_at),
        }
