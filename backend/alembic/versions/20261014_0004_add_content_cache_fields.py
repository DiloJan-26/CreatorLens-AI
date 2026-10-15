"""Add content cache and deduplication fields.

Revision ID: 20261014_0004
Revises: 20261014_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0004"
down_revision: str | None = "20261014_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("normalized_url", sa.Text()))
    op.add_column("content_items", sa.Column("content_hash", sa.String(64)))
    op.add_column("content_items", sa.Column("metadata_hash", sa.String(64)))
    op.add_column("content_items", sa.Column("transcript_hash", sa.String(64)))
    op.create_index("ix_content_items_normalized_url", "content_items", ["normalized_url"])
    op.create_index("ix_content_items_content_hash", "content_items", ["content_hash"])

    op.add_column("evidence_chunks", sa.Column("chunk_hash", sa.String(64)))
    op.add_column("evidence_chunks", sa.Column("embedding_hash", sa.String(64)))
    op.create_index("ix_evidence_chunks_chunk_hash", "evidence_chunks", ["chunk_hash"])
    op.create_index(
        "ix_evidence_chunks_embedding_hash", "evidence_chunks", ["embedding_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_chunks_embedding_hash", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_chunk_hash", table_name="evidence_chunks")
    op.drop_column("evidence_chunks", "embedding_hash")
    op.drop_column("evidence_chunks", "chunk_hash")
    op.drop_index("ix_content_items_content_hash", table_name="content_items")
    op.drop_index("ix_content_items_normalized_url", table_name="content_items")
    op.drop_column("content_items", "transcript_hash")
    op.drop_column("content_items", "metadata_hash")
    op.drop_column("content_items", "content_hash")
    op.drop_column("content_items", "normalized_url")
