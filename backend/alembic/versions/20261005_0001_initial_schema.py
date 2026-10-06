"""Create the Phase 1 PostgreSQL persistence schema.

Revision ID: 20261005_0001
Revises: None
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261005_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_1_url", sa.Text(), nullable=False),
        sa.Column("content_2_url", sa.Text(), nullable=False),
        sa.Column("content_1_platform", sa.String(32), nullable=False),
        sa.Column("content_2_platform", sa.String(32), nullable=False),
        sa.Column("youtube_url", sa.Text()),
        sa.Column("instagram_url", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_table(
        "content_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("extraction_status", sa.String(32), nullable=False),
        sa.Column("transcript_available", sa.Boolean(), nullable=False),
        sa.Column("transcript_segment_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_content_items_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_content_items"),
        sa.UniqueConstraint("project_id", "slot", name="uq_content_items_project_id"),
    )
    op.create_index("ix_content_items_project_id", "content_items", ["project_id"])
    op.create_index("ix_content_items_platform", "content_items", ["platform"])
    op.create_table(
        "metadata_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_item_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("caption", sa.Text()),
        sa.Column("creator", sa.Text()),
        sa.Column("creator_handle", sa.Text()),
        sa.Column("follower_count", sa.BigInteger()),
        sa.Column("subscriber_count", sa.BigInteger()),
        sa.Column("views", sa.BigInteger()),
        sa.Column("likes", sa.BigInteger()),
        sa.Column("comments", sa.BigInteger()),
        sa.Column("reactions", sa.BigInteger()),
        sa.Column("shares", sa.BigInteger()),
        sa.Column("hashtags", sa.JSON(), nullable=False),
        sa.Column("upload_date", sa.String(64)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("media_url", sa.Text()),
        sa.Column("audio_url", sa.Text()),
        sa.Column("engagement_rate", sa.Float()),
        sa.Column("missing_fields", sa.JSON(), nullable=False),
        sa.Column("transcript_language", sa.String(64)),
        sa.Column("detected_language", sa.String(64)),
        sa.Column("language_confidence", sa.Float()),
        sa.Column("transcript_source", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metric_source_note", sa.Text()),
        sa.Column("transcript_source_note", sa.Text()),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE", name="fk_metadata_snapshots_content_item_id_content_items"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_metadata_snapshots_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_metadata_snapshots"),
    )
    op.create_index("ix_metadata_snapshots_content_item_id", "metadata_snapshots", ["content_item_id"])
    op.create_index("ix_metadata_snapshots_project_id", "metadata_snapshots", ["project_id"])
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_item_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float()),
        sa.Column("end_time", sa.Float()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE", name="fk_transcript_segments_content_item_id_content_items"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_transcript_segments_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_transcript_segments"),
        sa.UniqueConstraint("content_item_id", "segment_index", name="uq_transcript_segments_content_item_id"),
    )
    op.create_index("ix_transcript_segments_content_item_id", "transcript_segments", ["content_item_id"])
    op.create_index("ix_transcript_segments_project_id", "transcript_segments", ["project_id"])
    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("content_item_id", sa.String(36)),
        sa.Column("slot", sa.String(32)),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float()),
        sa.Column("end_time", sa.Float()),
        sa.Column("title", sa.Text()),
        sa.Column("creator", sa.Text()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("citation_label", sa.Text(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE", name="fk_evidence_chunks_content_item_id_content_items"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_evidence_chunks_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_chunks"),
    )
    op.create_index("ix_evidence_chunks_project_id", "evidence_chunks", ["project_id"])
    op.create_index("ix_evidence_chunks_content_item_id", "evidence_chunks", ["content_item_id"])
    op.create_index("ix_evidence_chunks_source_type", "evidence_chunks", ["source_type"])
    op.create_index("ix_evidence_chunks_content_hash", "evidence_chunks", ["content_hash"])
    _create_chat_tables()
    _create_metric_sources_table()


def _create_chat_tables() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_chat_sessions_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_sessions"),
    )
    op.create_index("ix_chat_sessions_project_id", "chat_sessions", ["project_id"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE", name="fk_chat_messages_session_id_chat_sessions"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_chat_messages_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_project_id", "chat_messages", ["project_id"])
    op.create_table(
        "chat_citations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(32)),
        sa.Column("source_type", sa.String(32)),
        sa.Column("citation_label", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE", name="fk_chat_citations_message_id_chat_messages"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE", name="fk_chat_citations_session_id_chat_sessions"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_chat_citations_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_citations"),
    )
    op.create_index("ix_chat_citations_message_id", "chat_citations", ["message_id"])
    op.create_index("ix_chat_citations_session_id", "chat_citations", ["session_id"])
    op.create_index("ix_chat_citations_project_id", "chat_citations", ["project_id"])


def _create_metric_sources_table() -> None:
    op.create_table(
        "metric_sources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("source_platform", sa.String(32), nullable=False),
        sa.Column("source_method", sa.String(64), nullable=False),
        sa.Column("metric_scope", sa.String(64), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("views", sa.BigInteger()),
        sa.Column("likes", sa.BigInteger()),
        sa.Column("reactions", sa.BigInteger()),
        sa.Column("comments", sa.BigInteger()),
        sa.Column("shares", sa.BigInteger()),
        sa.Column("followers", sa.BigInteger()),
        sa.Column("engagement_rate", sa.Float()),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_metric_sources_project_id_projects"),
        sa.PrimaryKeyConstraint("id", name="pk_metric_sources"),
    )
    for column in ("project_id", "platform", "source_platform", "source_method", "metric_scope"):
        op.create_index(f"ix_metric_sources_{column}", "metric_sources", [column])


def downgrade() -> None:
    for column in ("metric_scope", "source_method", "source_platform", "platform", "project_id"):
        op.drop_index(f"ix_metric_sources_{column}", table_name="metric_sources")
    op.drop_table("metric_sources")
    op.drop_index("ix_chat_citations_project_id", table_name="chat_citations")
    op.drop_index("ix_chat_citations_session_id", table_name="chat_citations")
    op.drop_index("ix_chat_citations_message_id", table_name="chat_citations")
    op.drop_table("chat_citations")
    op.drop_index("ix_chat_messages_project_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_project_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index("ix_evidence_chunks_content_hash", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_source_type", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_content_item_id", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_project_id", table_name="evidence_chunks")
    op.drop_table("evidence_chunks")
    op.drop_index("ix_transcript_segments_project_id", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_content_item_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("ix_metadata_snapshots_project_id", table_name="metadata_snapshots")
    op.drop_index("ix_metadata_snapshots_content_item_id", table_name="metadata_snapshots")
    op.drop_table("metadata_snapshots")
    op.drop_index("ix_content_items_platform", table_name="content_items")
    op.drop_index("ix_content_items_project_id", table_name="content_items")
    op.drop_table("content_items")
    op.drop_table("projects")
