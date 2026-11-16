from typing import Any
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.db.models.metric_source import MetricSource
from app.db.repositories._utils import iso_timestamp, utc_now


class MetricSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        project_id: str,
        platform: str,
        source_platform: str,
        source_method: str,
        metric_scope: str,
        url: str | None = None,
        views: int | None = None,
        likes: int | None = None,
        reactions: int | None = None,
        comments: int | None = None,
        shares: int | None = None,
        followers: int | None = None,
        engagement_rate: float | None = None,
        confidence: str = "medium",
        note: str | None = None,
        record_id: str | None = None,
        slot: str | None = None,
        content_item_id: str | None = None,
    ) -> dict[str, Any]:
        if slot is not None and slot not in {"content_1", "content_2"}:
            raise ValueError("Invalid content slot.")
        if content_item_id is not None:
            from app.db.models.content_item import ContentItem
            item = self.session.get(ContentItem, content_item_id)
            if item is None or item.project_id != project_id or item.slot != slot or (metric_scope in {"native", "verified_override"} and item.platform != source_platform):
                raise ValueError("Metric source content identity does not belong to this project/slot.")
        existing = None
        if record_id is not None:
            existing = self.session.get(MetricSource, record_id)
            if existing is not None and (existing.project_id != project_id or existing.slot != slot):
                raise ValueError("Metric source identity cannot be reassigned.")
        else:
            existing = self.latest(
                project_id=project_id,
                source_platform=source_platform,
                metric_scope=metric_scope,
                source_method=source_method,
                slot=slot,
            )

        timestamp = utc_now()
        if existing is None:
            existing = MetricSource(
                id=record_id or str(uuid4()),
                project_id=project_id,
                platform=platform,
                source_platform=source_platform,
                source_method=source_method,
                metric_scope=metric_scope,
                confidence=confidence,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(existing)

        existing.slot = slot
        existing.content_item_id = content_item_id
        existing.platform = platform
        existing.source_platform = source_platform
        existing.source_method = source_method
        existing.metric_scope = metric_scope
        existing.url = url
        existing.views = views
        existing.likes = likes
        existing.reactions = reactions
        existing.comments = comments
        existing.shares = shares
        existing.followers = followers
        existing.engagement_rate = engagement_rate
        existing.confidence = confidence
        existing.note = note
        existing.updated_at = timestamp
        self.session.flush()
        return self.to_record(existing)

    def get(self, project_id: str, record_id: str) -> dict[str, Any] | None:
        model = self.session.scalar(
            select(MetricSource).where(
                MetricSource.project_id == project_id,
                MetricSource.id == record_id,
            )
        )
        return self.to_record(model) if model is not None else None

    def list(self, project_id: str) -> list[dict[str, Any]]:
        models = self.session.scalars(
            select(MetricSource)
            .where(MetricSource.project_id == project_id)
            .order_by(desc(MetricSource.updated_at))
        ).all()
        return [self.to_record(model) for model in models]

    def latest(
        self,
        *,
        project_id: str,
        source_platform: str,
        metric_scope: str,
        source_method: str | None = None,
        slot: str | None = None,
    ) -> MetricSource | None:
        statement = select(MetricSource).where(
            MetricSource.project_id == project_id,
            MetricSource.slot == slot,
            MetricSource.source_platform == source_platform,
            MetricSource.metric_scope == metric_scope,
        )
        if source_method is not None:
            statement = statement.where(
                MetricSource.source_method == source_method
            )
        return self.session.scalar(
            statement.order_by(desc(MetricSource.updated_at)).limit(1)
        )

    def delete(self, project_id: str, record_id: str) -> None:
        self.session.execute(
            delete(MetricSource).where(
                MetricSource.project_id == project_id,
                MetricSource.id == record_id,
            )
        )
        self.session.flush()

    @staticmethod
    def to_record(model: MetricSource) -> dict[str, Any]:
        return {
            "id": model.id,
            "project_id": model.project_id,
            "platform": model.platform,
            "source_platform": model.source_platform,
            "source_method": model.source_method,
            "metric_scope": model.metric_scope,
            "slot": model.slot,
            "content_item_id": model.content_item_id,
            "identity_status": "bound" if model.slot else "legacy_unresolved",
            "url": model.url,
            "views": model.views,
            "likes": model.likes,
            "reactions": model.reactions,
            "comments": model.comments,
            "shares": model.shares,
            "followers": model.followers,
            "engagement_rate": model.engagement_rate,
            "confidence": model.confidence,
            "note": model.note,
            "created_at": iso_timestamp(model.created_at),
            "updated_at": iso_timestamp(model.updated_at),
        }
