"""Create event_queue table for tiered event aggregation

Revision ID: 005_add_event_queue
Revises: f9861a2caa12
Create Date: 2026-06-15

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '005_add_event_queue'
down_revision = 'f9861a2caa12'
branch_labels = None
depends_on = None


def upgrade():
    """Create event_queue table."""

    op.create_table(
        'event_queue',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('tier', sa.String(10), nullable=False, server_default='P2'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('batch_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Indexes
    op.create_index('idx_event_queue_user_tier_status', 'event_queue',
                    ['user_id', 'tier', 'status'], unique=False)
    op.create_index('idx_event_queue_created_at', 'event_queue',
                    ['created_at'], unique=False)
    op.create_index('idx_event_queue_batch_id', 'event_queue',
                    ['batch_id'], unique=False)


def downgrade():
    """Drop event_queue table."""
    op.drop_index('idx_event_queue_batch_id', table_name='event_queue')
    op.drop_index('idx_event_queue_created_at', table_name='event_queue')
    op.drop_index('idx_event_queue_user_tier_status', table_name='event_queue')
    op.drop_table('event_queue')