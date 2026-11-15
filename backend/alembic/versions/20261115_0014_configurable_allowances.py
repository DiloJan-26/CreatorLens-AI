"""Permit configured new grants and bounded concurrent analyses; preserve all history.

Quiesce old API and workers before upgrade. New admissions serialize on entitlement
rows; old and new quota policies must never run concurrently during rollout.
"""
from alembic import op
import sqlalchemy as sa
revision = "20261115_0014"
down_revision = "20261114_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("credit_bounds", "user_entitlements", type_="check")
    op.create_check_constraint("credit_bounds", "user_entitlements", "granted >= 0 AND consumed >= 0 AND reserved >= 0 AND consumed + reserved <= granted")
    predicate = sa.text("state IN ('reserved','processing','needs_reconciliation')")
    op.create_index("uq_active_analysis_per_project", "analysis_reservations", ["project_id"], unique=True, postgresql_where=predicate)
    op.drop_index("uq_active_analysis_per_user", table_name="analysis_reservations")


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM user_entitlements WHERE granted <> 5 LIMIT 1")).first() or connection.execute(sa.text("SELECT user_id FROM analysis_reservations WHERE state IN ('reserved','processing','needs_reconciliation') GROUP BY user_id HAVING count(*) > 1 LIMIT 1")).first():
        raise RuntimeError("Configured allowances exist; preserve history and roll forward.")
    op.create_index("uq_active_analysis_per_user", "analysis_reservations", ["user_id"], unique=True, postgresql_where=sa.text("state IN ('reserved','processing','needs_reconciliation')"))
    op.drop_index("uq_active_analysis_per_project", table_name="analysis_reservations")
    op.drop_constraint("credit_bounds", "user_entitlements", type_="check")
    op.create_check_constraint("credit_bounds", "user_entitlements", "granted = 5 AND consumed >= 0 AND reserved >= 0 AND consumed + reserved <= granted")
