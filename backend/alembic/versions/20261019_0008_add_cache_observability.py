"""Persist extraction and embedding cache observations.

Revision ID: 20261019_0008
Revises: 20261019_0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_0008"
down_revision: str | None = "20261019_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("last_extraction_cache_hit", sa.Boolean()),
    )
    op.add_column(
        "content_items",
        sa.Column("last_embedding_reused", sa.Boolean()),
    )


def downgrade() -> None:
    op.drop_column("content_items", "last_embedding_reused")
    op.drop_column("content_items", "last_extraction_cache_hit")
