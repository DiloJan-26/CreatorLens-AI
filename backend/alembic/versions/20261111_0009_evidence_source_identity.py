"""Expand source identity and evidence revisions without guessing historical slots."""
from alembic import op
import sqlalchemy as sa

revision = "20261111_0009"
down_revision = "20261019_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("metric_sources", sa.Column("slot", sa.String(32), nullable=True))
    op.add_column("metric_sources", sa.Column("content_item_id", sa.String(36), nullable=True))
    op.create_index("ix_metric_sources_content_item_id", "metric_sources", ["content_item_id"])
    op.create_index("uq_metric_sources_slot_identity", "metric_sources",
        ["project_id", "slot", "source_platform", "metric_scope", "source_method"], unique=True,
        postgresql_where=sa.text("slot IS NOT NULL"), sqlite_where=sa.text("slot IS NOT NULL"))
    op.add_column("evidence_chunks", sa.Column("evidence_revision", sa.String(64), nullable=True))
    op.create_index("ix_evidence_chunks_evidence_revision", "evidence_chunks", ["evidence_revision"])
    # Historical platform-only records remain null/unresolved. No copy/backfill.


def downgrade():
    op.drop_index("ix_evidence_chunks_evidence_revision", table_name="evidence_chunks")
    op.drop_column("evidence_chunks", "evidence_revision")
    op.drop_index("uq_metric_sources_slot_identity", table_name="metric_sources")
    op.drop_index("ix_metric_sources_content_item_id", table_name="metric_sources")
    op.drop_column("metric_sources", "content_item_id")
    op.drop_column("metric_sources", "slot")
