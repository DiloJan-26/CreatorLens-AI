"""Add LLM and cost observability persistence.

Revision ID: 20261019_0007
Revises: 20261018_0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_0007"
down_revision: str | None = "20261018_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(128)),
        sa.Column("retrieval_run_id", sa.String(36)),
        sa.Column("langsmith_trace_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("llm_provider", sa.String(32), nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("prompt_name", sa.String(128)),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("retrieval_latency_ms", sa.Integer()),
        sa.Column("llm_latency_ms", sa.Integer()),
        sa.Column("retrieved_chunk_count", sa.Integer()),
        sa.Column(
            "source_balance",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("cache_hit", sa.Boolean()),
        sa.Column("cache_miss", sa.Boolean()),
        sa.Column("transcript_provider", sa.String(64)),
        sa.Column("transcript_fallback_used", sa.Boolean()),
        sa.Column("embedding_reused", sa.Boolean()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_llm_runs_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            ondelete="SET NULL",
            name="fk_llm_runs_retrieval_run_id_retrieval_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_runs"),
    )
    op.create_index("ix_llm_runs_project_id", "llm_runs", ["project_id"])
    op.create_index("ix_llm_runs_session_id", "llm_runs", ["session_id"])
    op.create_index(
        "ix_llm_runs_retrieval_run_id", "llm_runs", ["retrieval_run_id"]
    )
    op.create_index(
        "ix_llm_runs_langsmith_trace_id", "llm_runs", ["langsmith_trace_id"]
    )
    op.create_index("ix_llm_runs_status", "llm_runs", ["status"])
    op.create_index("ix_llm_runs_llm_model", "llm_runs", ["llm_model"])
    op.create_index(
        "ix_llm_runs_prompt_version", "llm_runs", ["prompt_version"]
    )
    op.create_index("ix_llm_runs_created_at", "llm_runs", ["created_at"])

    op.create_table(
        "cost_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("llm_run_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("llm_provider", sa.String(32), nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 8)),
        sa.Column("pricing_source", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["llm_run_id"],
            ["llm_runs.id"],
            ondelete="CASCADE",
            name="fk_cost_events_llm_run_id_llm_runs",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_cost_events_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cost_events"),
    )
    op.create_index(
        "ix_cost_events_llm_run_id", "cost_events", ["llm_run_id"]
    )
    op.create_index(
        "ix_cost_events_project_id", "cost_events", ["project_id"]
    )
    op.create_index("ix_cost_events_llm_model", "cost_events", ["llm_model"])
    op.create_index(
        "ix_cost_events_created_at", "cost_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_cost_events_created_at", table_name="cost_events")
    op.drop_index("ix_cost_events_llm_model", table_name="cost_events")
    op.drop_index("ix_cost_events_project_id", table_name="cost_events")
    op.drop_index("ix_cost_events_llm_run_id", table_name="cost_events")
    op.drop_table("cost_events")
    op.drop_index("ix_llm_runs_created_at", table_name="llm_runs")
    op.drop_index("ix_llm_runs_prompt_version", table_name="llm_runs")
    op.drop_index("ix_llm_runs_llm_model", table_name="llm_runs")
    op.drop_index("ix_llm_runs_status", table_name="llm_runs")
    op.drop_index("ix_llm_runs_langsmith_trace_id", table_name="llm_runs")
    op.drop_index("ix_llm_runs_retrieval_run_id", table_name="llm_runs")
    op.drop_index("ix_llm_runs_session_id", table_name="llm_runs")
    op.drop_index("ix_llm_runs_project_id", table_name="llm_runs")
    op.drop_table("llm_runs")
