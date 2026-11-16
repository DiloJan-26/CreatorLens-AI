"""One versioned semantic snapshot per content, evidence and analysis identity."""
from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class SemanticSnapshot(Base):
    __tablename__ = "semantic_snapshots"
    __table_args__ = (Index("ix_semantic_snapshots_project_slot", "project_id", "slot"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slot: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    processing: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
