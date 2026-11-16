"""Add versioned semantic snapshot storage; no historical backfill."""
from alembic import op
import sqlalchemy as sa
revision = '20261113_0010'
down_revision = '20261111_0009'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('semantic_snapshots',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('content_id', sa.String(36), nullable=False),
        sa.Column('slot', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('processing', sa.JSON(), nullable=False),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('model_id', sa.String(128), nullable=False),
        sa.Column('prompt_version', sa.String(32), nullable=False),
        sa.Column('schema_version', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_semantic_snapshots_project_slot','semantic_snapshots',['project_id','slot'])

def downgrade():
    op.drop_index('ix_semantic_snapshots_project_slot', table_name='semantic_snapshots')
    op.drop_table('semantic_snapshots')
