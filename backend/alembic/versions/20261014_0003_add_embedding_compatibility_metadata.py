"""Add embedding compatibility metadata to evidence chunks.

Revision ID: 20261014_0003
Revises: 20261007_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0003"
down_revision: str | None = "20261007_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_chunks",
        sa.Column("embedding_model_name", sa.String(255)),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("embedding_model_version", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_column("evidence_chunks", "embedding_model_version")
    op.drop_column("evidence_chunks", "embedding_model_name")
