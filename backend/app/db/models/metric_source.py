from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricSource(Base):
    """Existing V1 verified-metrics persistence retained during Phase 1."""

    __tablename__ = "metric_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_method: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    reactions: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    followers: Mapped[int | None] = mapped_column(BigInteger)
    engagement_rate: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
