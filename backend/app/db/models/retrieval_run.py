from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_filters: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    result_chunk_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
