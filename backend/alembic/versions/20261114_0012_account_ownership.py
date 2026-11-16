"""Add account ownership and durable admissions; quarantine historical projects."""
from alembic import op
import sqlalchemy as sa
revision = "20261114_0012"
down_revision = "20261113_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("app_users", sa.Column("id",sa.String(36),primary_key=True), sa.Column("email",sa.String(512)), sa.Column("display_name",sa.String(512)), sa.Column("avatar_url",sa.Text()), sa.Column("status",sa.String(24),nullable=False), sa.Column("role",sa.String(16),nullable=False), sa.Column("created_at",sa.DateTime(timezone=True),nullable=False), sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("owner_user_id",sa.String(36),nullable=True))
        batch.create_foreign_key("fk_projects_owner_user_id_app_users","app_users",["owner_user_id"],["id"])
        batch.create_index("ix_projects_owner_user_id",["owner_user_id"])
    op.create_table("revoked_sessions",sa.Column("id",sa.String(36),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("app_users.id"),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_revoked_sessions_user_id","revoked_sessions",["user_id"])
    op.create_table("user_entitlements",sa.Column("user_id",sa.String(36),sa.ForeignKey("app_users.id"),primary_key=True),sa.Column("granted",sa.Integer(),nullable=False),sa.Column("consumed",sa.Integer(),nullable=False),sa.Column("reserved",sa.Integer(),nullable=False),sa.CheckConstraint("granted = 5 AND consumed >= 0 AND reserved >= 0 AND consumed + reserved <= granted",name="credit_bounds"))
    op.create_table("analysis_reservations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("app_users.id"),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("idempotency_key",sa.String(128),nullable=False),sa.Column("fingerprint",sa.String(64),nullable=False),sa.Column("state",sa.String(32),nullable=False),sa.Column("completion_mode",sa.String(32)),sa.Column("job_id",sa.String(36)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("user_id","idempotency_key"))
    op.create_index("ix_analysis_reservations_user_id","analysis_reservations",["user_id"])
    op.create_index("ix_analysis_reservations_project_id","analysis_reservations",["project_id"])
    predicate=sa.text("state IN ('reserved','processing','needs_reconciliation')")
    op.create_index("uq_active_analysis_per_user","analysis_reservations",["user_id"],unique=True,postgresql_where=predicate,sqlite_where=predicate)
    op.create_table("usage_events",sa.Column("id",sa.String(36),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("app_users.id"),nullable=False),sa.Column("event_key",sa.String(180),nullable=False,unique=True),sa.Column("kind",sa.String(48),nullable=False),sa.Column("reference_id",sa.String(128),nullable=False),sa.Column("details",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_usage_events_user_id","usage_events",["user_id"])
    op.create_table("budget_accounts",sa.Column("id",sa.String(48),primary_key=True),sa.Column("reserved_usd",sa.Numeric(24,12),nullable=False),sa.CheckConstraint("reserved_usd >= 0",name="budget_nonnegative"))
    op.execute(sa.text("INSERT INTO budget_accounts (id,reserved_usd) VALUES ('global',0)"))
    op.create_table("provider_operations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("reservation_id",sa.String(36),sa.ForeignKey("analysis_reservations.id"),nullable=False),sa.Column("project_id",sa.String(36),nullable=False),sa.Column("user_id",sa.String(36),sa.ForeignKey("app_users.id"),nullable=False),sa.Column("kind",sa.String(32),nullable=False),sa.Column("slot",sa.String(16),nullable=False),sa.Column("attempt",sa.Integer(),nullable=False),sa.Column("state",sa.String(32),nullable=False),sa.Column("ceiling_usd",sa.Numeric(24,12),nullable=False),sa.Column("snapshot_id",sa.String(64)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("reservation_id","kind","slot","attempt"))
    for column in ("reservation_id","project_id","user_id"):
        op.create_index("ix_provider_operations_"+column,"provider_operations",[column])
    op.create_table("dispatch_outbox",sa.Column("id",sa.String(64),primary_key=True),sa.Column("reservation_id",sa.String(36),sa.ForeignKey("analysis_reservations.id"),nullable=False),sa.Column("task_name",sa.String(64),nullable=False),sa.Column("argument",sa.String(64),nullable=False),sa.Column("state",sa.String(24),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))


    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("CREATE FUNCTION reject_usage_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Usage events are append-only'; END $$"))
        op.execute(sa.text("CREATE TRIGGER usage_events_append_only BEFORE UPDATE OR DELETE ON usage_events FOR EACH ROW EXECUTE FUNCTION reject_usage_event_mutation()"))
        for parent in ("content_items","chat_sessions","chat_messages","llm_runs"):
            op.create_unique_constraint("uq_"+parent+"_id_project",parent,["id","project_id"])
        relations=[("metadata_snapshots","content_item_id","content_items"),("transcript_segments","content_item_id","content_items"),("evidence_chunks","content_item_id","content_items"),("semantic_snapshots","content_id","content_items"),("chat_messages","session_id","chat_sessions"),("chat_citations","session_id","chat_sessions"),("chat_citations","message_id","chat_messages"),("cost_events","llm_run_id","llm_runs")]
        for child,column,parent in relations:
            # NOT VALID preserves historical mismatches without accepting new mismatched writes.
            # Deletion stays governed by existing reviewed single-column CASCADE behavior.
            name="fk_"+child+"_"+column+"_membership"
            op.execute(sa.text(f'ALTER TABLE {child} ADD CONSTRAINT {name} FOREIGN KEY ({column},project_id) REFERENCES {parent}(id,project_id) NOT VALID'))


def downgrade():
    raise RuntimeError("Account/credit history must be preserved. Use a reviewed roll-forward recovery; destructive downgrade is disabled.")
