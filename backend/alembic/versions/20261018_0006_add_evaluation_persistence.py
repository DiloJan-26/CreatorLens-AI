"""Add evaluation persistence.

Revision ID: 20261018_0006
Revises: 20261018_0005
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261018_0006"
down_revision: str | None = "20261018_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_datasets"),
        sa.UniqueConstraint(
            "name", "version", name="uq_evaluation_datasets_name_version"
        ),
    )
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("case_key", sa.String(128), nullable=False),
        sa.Column("project_fixture", sa.String(128), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer_type", sa.String(32), nullable=False),
        sa.Column(
            "required_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "forbidden_claims", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "rubric", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["evaluation_datasets.id"],
            ondelete="CASCADE",
            name="fk_evaluation_cases_dataset_id_evaluation_datasets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_cases"),
        sa.UniqueConstraint(
            "dataset_id",
            "case_key",
            name="uq_evaluation_cases_dataset_id_case_key",
        ),
    )
    op.create_index(
        "ix_evaluation_cases_dataset_id", "evaluation_cases", ["dataset_id"]
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evaluator", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128)),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "aggregate_metrics",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["evaluation_datasets.id"],
            ondelete="CASCADE",
            name="fk_evaluation_runs_dataset_id_evaluation_datasets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_runs"),
    )
    op.create_index(
        "ix_evaluation_runs_dataset_id", "evaluation_runs", ["dataset_id"]
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index(
        "ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"]
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("evaluation_case_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("answer_type", sa.String(32)),
        sa.Column("answer_text", sa.Text()),
        sa.Column(
            "citation_labels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "metric_scores", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "rubric_results", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"],
            ["evaluation_cases.id"],
            ondelete="CASCADE",
            name="fk_evaluation_results_evaluation_case_id_evaluation_cases",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
            name="fk_evaluation_results_run_id_evaluation_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_results"),
        sa.UniqueConstraint(
            "run_id",
            "evaluation_case_id",
            name="uq_evaluation_results_run_id_evaluation_case_id",
        ),
    )
    op.create_index(
        "ix_evaluation_results_run_id", "evaluation_results", ["run_id"]
    )
    op.create_index(
        "ix_evaluation_results_evaluation_case_id",
        "evaluation_results",
        ["evaluation_case_id"],
    )
    op.create_index(
        "ix_evaluation_results_status", "evaluation_results", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_status", table_name="evaluation_results")
    op.drop_index(
        "ix_evaluation_results_evaluation_case_id",
        table_name="evaluation_results",
    )
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_dataset_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_dataset_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_datasets")
