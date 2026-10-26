"""Add retrieval run observability.

Revision ID: 20261018_0005
Revises: 20261014_0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_0005"
down_revision: str | None = "20261014_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieval_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_top_k", sa.Integer(), nullable=False),
        sa.Column(
            "candidate_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "applied_filters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result_chunk_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_retrieval_runs_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_runs"),
    )
    op.create_index(
        "ix_retrieval_runs_project_id", "retrieval_runs", ["project_id"]
    )
    op.create_index(
        "ix_retrieval_runs_retrieval_mode",
        "retrieval_runs",
        ["retrieval_mode"],
    )
    op.create_index("ix_retrieval_runs_status", "retrieval_runs", ["status"])
    op.create_index(
        "ix_retrieval_runs_created_at", "retrieval_runs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_runs_created_at", table_name="retrieval_runs")
    op.drop_index("ix_retrieval_runs_status", table_name="retrieval_runs")
    op.drop_index(
        "ix_retrieval_runs_retrieval_mode", table_name="retrieval_runs"
    )
    op.drop_index("ix_retrieval_runs_project_id", table_name="retrieval_runs")
    op.drop_table("retrieval_runs")
