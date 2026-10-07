"""Add persisted Phase 2 ingestion jobs.

Revision ID: 20261007_0002
Revises: 20261005_0001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261007_0002"
down_revision: str | None = "20261005_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("celery_task_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_ingestion_jobs_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint(
            "celery_task_id",
            name="uq_ingestion_jobs_celery_task_id",
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_project_id",
        "ingestion_jobs",
        ["project_id"],
    )
    op.create_index(
        "ix_ingestion_jobs_status",
        "ingestion_jobs",
        ["status"],
    )
    op.create_index(
        "uq_ingestion_jobs_active_project",
        "ingestion_jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(
            "status NOT IN ('READY', 'PARTIAL_READY', 'FAILED')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ingestion_jobs_active_project",
        table_name="ingestion_jobs",
    )
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_project_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
