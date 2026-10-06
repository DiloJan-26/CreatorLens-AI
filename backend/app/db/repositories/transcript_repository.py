from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.transcript_segment import TranscriptSegment as TranscriptSegmentModel
from app.db.repositories._utils import iso_timestamp, utc_now
from app.models.video import TranscriptSegment


class TranscriptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace(
        self,
        *,
        project_id: str,
        content_item_id: str,
        slot: str,
        platform: str,
        segments: list[TranscriptSegment],
    ) -> None:
        self.session.execute(
            delete(TranscriptSegmentModel).where(
                TranscriptSegmentModel.project_id == project_id,
                TranscriptSegmentModel.slot == slot,
            )
        )
        timestamp = utc_now()
        self.session.add_all(
            [
                TranscriptSegmentModel(
                    id=str(uuid4()),
                    content_item_id=content_item_id,
                    project_id=project_id,
                    slot=slot,
                    platform=platform,
                    segment_index=segment.segment_index,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text=segment.text,
                    created_at=timestamp,
                )
                for segment in segments
            ]
        )
        self.session.flush()

    def list(
        self, *, project_id: str, slot: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        statement = (
            select(TranscriptSegmentModel)
            .where(
                TranscriptSegmentModel.project_id == project_id,
                TranscriptSegmentModel.slot == slot,
            )
            .order_by(TranscriptSegmentModel.segment_index)
        )
        if limit is not None:
            statement = statement.limit(max(1, min(limit, 100)))
        segments = self.session.scalars(statement).all()
        return [self.to_record(segment) for segment in segments]

    @staticmethod
    def to_record(segment: TranscriptSegmentModel) -> dict[str, Any]:
        return {
            "id": segment.id,
            "video_id": segment.content_item_id,
            "project_id": segment.project_id,
            "slot": segment.slot,
            "platform": segment.platform,
            "segment_index": segment.segment_index,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text,
            "created_at": iso_timestamp(segment.created_at),
        }
