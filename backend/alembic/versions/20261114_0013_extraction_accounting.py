"""Add nullable bounded-extraction accounting; preserve historical operations."""
from alembic import op
import sqlalchemy as sa
revision = "20261114_0013"
down_revision = "20261114_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_operations", sa.Column("operation_key", sa.String(64), nullable=True))
    op.add_column("provider_operations", sa.Column("billing_pool", sa.String(128), nullable=True))
    op.add_column("provider_operations", sa.Column("reserved_quantity", sa.Integer(), nullable=True))
    op.add_column("provider_operations", sa.Column("provider_details", sa.JSON(), nullable=True))
    op.create_check_constraint("provider_quantity_nonnegative","provider_operations","reserved_quantity IS NULL OR reserved_quantity >= 0")
    op.create_index("uq_provider_operations_operation_key", "provider_operations", ["operation_key"], unique=True)
    op.create_index("ix_provider_operations_billing_pool", "provider_operations", ["billing_pool"])


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM provider_operations WHERE operation_key IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Extraction accounting history exists; preserve schema and roll forward.")
    op.drop_constraint("provider_quantity_nonnegative","provider_operations",type_="check")
    op.drop_index("ix_provider_operations_billing_pool", table_name="provider_operations")
    op.drop_index("uq_provider_operations_operation_key", table_name="provider_operations")
    for name in ("provider_details", "reserved_quantity", "billing_pool", "operation_key"):
        op.drop_column("provider_operations", name)
