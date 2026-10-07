from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


ACTIVE_JOB_PREDICATE = text(
    "status NOT IN ('READY', 'PARTIAL_READY', 'FAILED')"
)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index(
            "uq_ingestion_jobs_active_project",
            "project_id",
            unique=True,
            postgresql_where=ACTIVE_JOB_PREDICATE,
            sqlite_where=ACTIVE_JOB_PREDICATE,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

