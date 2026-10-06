from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetadataSnapshot(Base):
    __tablename__ = "metadata_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    creator: Mapped[str | None] = mapped_column(Text)
    creator_handle: Mapped[str | None] = mapped_column(Text)
    follower_count: Mapped[int | None] = mapped_column(BigInteger)
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    reactions: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    upload_date: Mapped[str | None] = mapped_column(String(64))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(Text)
    engagement_rate: Mapped[float | None] = mapped_column(Float)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    transcript_language: Mapped[str | None] = mapped_column(String(64))
    detected_language: Mapped[str | None] = mapped_column(String(64))
    language_confidence: Mapped[float | None] = mapped_column(Float)
    transcript_source: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    metric_source_note: Mapped[str | None] = mapped_column(Text)
    transcript_source_note: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
