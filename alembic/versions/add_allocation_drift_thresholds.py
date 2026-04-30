"""Add thresholds table for allocation drift detection

Revision ID: add_allocation_drift_thresholds
Revises: gamma_strategy_cost_tracking
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_allocation_drift_thresholds'
down_revision = 'gamma_strategy_cost_tracking'
branch_labels = None
depends_on = None

def upgrade():
    # Create thresholds table if not exists
    op.create_table(
        'thresholds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('type', sa.String(100), nullable=False),
        sa.Column('threshold_value', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'type', name='uq_user_threshold_type'),
        sa.Index('idx_user_id', 'user_id'),
        sa.Index('idx_type', 'type')
    )
    
    # Insert default allocation drift thresholds for the primary user
    # These can be overridden per user via the API
    op.execute("""
        INSERT INTO thresholds (user_id, type, threshold_value)
        VALUES 
            ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_warning', 3.0),
            ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_alert', 5.0),
            ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_critical', 10.0)
        ON CONFLICT (user_id, type) DO UPDATE
        SET threshold_value = EXCLUDED.threshold_value
    """)

def downgrade():
    op.drop_table('thresholds')
