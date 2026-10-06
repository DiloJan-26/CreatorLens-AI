from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        index=True,
    )
    slot: Mapped[str | None] = mapped_column(String(32))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float | None] = mapped_column(Float)
    end_time: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(Text)
    creator: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    citation_label: Mapped[str] = mapped_column(Text, nullable=False)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
