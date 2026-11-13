"""Add nullable operation telemetry; preserve historical estimates and rows."""
from alembic import op
import sqlalchemy as sa
revision='20261113_0011'
down_revision='20261113_0010'
branch_labels=None
depends_on=None


def upgrade():
    # PostgreSQL is the deployed observability store. SQLite tests use nullable
    # model metadata; avoid a parent-table rebuild/cascade merely to emulate ALTER.
    if op.get_bind().dialect.name=='postgresql':
        op.alter_column('llm_runs','project_id',existing_type=sa.String(36),nullable=True)
        op.alter_column('cost_events','project_id',existing_type=sa.String(36),nullable=True)
    for name,type_ in [('operation_type',sa.String(64)),('execution_mode',sa.String(32)),('provider_invocation_count',sa.Integer()),
        ('end_to_end_latency_ms',sa.Integer()),('context_latency_ms',sa.Integer()),('deterministic_latency_ms',sa.Integer()),('telemetry',sa.JSON())]:
        op.add_column('llm_runs',sa.Column(name,type_,nullable=True))
    op.add_column('cost_events',sa.Column('estimate_details',sa.JSON(),nullable=True))
    op.add_column('cost_events',sa.Column('priced_subtotal_usd',sa.Numeric(18,8),nullable=True))
    op.add_column('cost_events',sa.Column('cost_status',sa.String(32),nullable=True))
    op.add_column('cost_events',sa.Column('event_key',sa.String(64),nullable=True))
    op.create_index('uq_cost_events_event_key','cost_events',['event_key'],unique=True)


def downgrade():
    # Never erase projectless diagnostic history to satisfy the older constraint.
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM llm_runs WHERE project_id IS NULL')).scalar() or op.get_bind().execute(sa.text('SELECT COUNT(*) FROM cost_events WHERE project_id IS NULL')).scalar():
        raise RuntimeError('Downgrade requires reviewed preservation of projectless diagnostic rows; no rows were deleted.')
    if op.get_bind().dialect.name=='postgresql':
        op.alter_column('cost_events','project_id',existing_type=sa.String(36),nullable=False)
        op.alter_column('llm_runs','project_id',existing_type=sa.String(36),nullable=False)
    op.drop_index('uq_cost_events_event_key',table_name='cost_events')
    op.drop_column('cost_events','event_key')
    op.drop_column('cost_events','cost_status')
    op.drop_column('cost_events','priced_subtotal_usd')
    op.drop_column('cost_events','estimate_details')
    for name in ('telemetry','deterministic_latency_ms','context_latency_ms','end_to_end_latency_ms','provider_invocation_count','execution_mode','operation_type'):
        op.drop_column('llm_runs',name)
