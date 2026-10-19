from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmRun(Base):
    __tablename__ = "llm_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(128), index=True)
    retrieval_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("retrieval_runs.id", ondelete="SET NULL"),
        index=True,
    )
    langsmith_trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prompt_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(32), index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    retrieved_chunk_count: Mapped[int | None] = mapped_column(Integer)
    source_balance: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    cache_hit: Mapped[bool | None] = mapped_column(Boolean)
    cache_miss: Mapped[bool | None] = mapped_column(Boolean)
    transcript_provider: Mapped[str | None] = mapped_column(String(64))
    transcript_fallback_used: Mapped[bool | None] = mapped_column(Boolean)
    embedding_reused: Mapped[bool | None] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CostEvent(Base):
    __tablename__ = "cost_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    llm_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("llm_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    pricing_source: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
