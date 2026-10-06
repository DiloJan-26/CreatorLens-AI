from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (UniqueConstraint("project_id", "slot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    transcript_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    transcript_segment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
