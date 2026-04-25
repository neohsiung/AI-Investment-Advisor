"""Add enterprise queue and telemetry tables

Revision ID: 004
Revises: 003
Create Date: 2026-04-23 12:00:00.000000

This migration adds the core tables for the Enterprise Version:
- report_jobs: Task queue and state tracking
- job_telemetry: Performance metrics per stage
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003_add_report_jobs_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create report_jobs table
    op.create_table(
        'report_jobs',
        sa.Column('job_id', sa.String(36), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, index=True),
        sa.Column('report_type', sa.String(20), nullable=False, 
                  comment='daily, weekly, or monthly'),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='queued',
                  comment='queued, running, completed, failed, dlq'),
        sa.Column('priority', sa.Integer(), nullable=False, default=50,
                  comment='0-100 priority level'),
        sa.Column('current_stage', sa.Integer(), nullable=False, default=1,
                  comment='1-5 stage number for checkpoint resume'),
        sa.Column('checkpoint_data', postgresql.JSON(), nullable=True,
                  comment='Serialized checkpoint state'),
        sa.Column('report_id', sa.String(36), nullable=True,
                  comment='FK to reports table'),
        sa.Column('generation_model', sa.String(100), nullable=True,
                  comment='Model used for synthesis (smart/fast/nano)'),
        sa.Column('error_message', sa.Text(), nullable=True,
                  comment='Error details if failed'),
        sa.Column('last_checkpoint_stage', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, 
                  server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, 
                  server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    
    # Create indexes
    op.create_index('idx_report_jobs_user_status', 'report_jobs', 
                    ['user_id', 'status'])
    op.create_index('idx_report_jobs_status_priority', 'report_jobs', 
                    ['status', 'priority'])
    op.create_index('idx_report_jobs_created', 'report_jobs', ['created_at'])

    # Create job_telemetry table
    op.create_table(
        'job_telemetry',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True, 
                  autoincrement=True),
        sa.Column('job_id', sa.String(36), nullable=False, index=True),
        sa.Column('stage', sa.Integer(), nullable=False,
                  comment='1-5 stage number'),
        sa.Column('stage_name', sa.String(50), nullable=False,
                  comment='queue_init, fetch_data, assemble_context, synthesis, dispatch'),
        sa.Column('status', sa.String(20), nullable=False,
                  comment='success, timeout, error, fallback'),
        sa.Column('duration_ms', sa.Integer(), nullable=False,
                  comment='Stage duration in milliseconds'),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False, 
                  server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['report_jobs.job_id']),
    )
    
    # Create indexes
    op.create_index('idx_job_telemetry_job_stage', 'job_telemetry', 
                    ['job_id', 'stage'])
    op.create_index('idx_job_telemetry_created', 'job_telemetry', ['created_at'])

    # Modify reports table to add job_id if not exists
    with op.batch_alter_table('reports', schema=None) as batch_op:
        if not batch_op.columns.get('job_id'):
            batch_op.add_column(
                sa.Column('job_id', sa.String(36), nullable=True, index=True)
            )
        if not batch_op.columns.get('generation_model'):
            batch_op.add_column(
                sa.Column('generation_model', sa.String(100), nullable=True,
                          comment='Model used for generation')
            )
        if not batch_op.columns.get('is_draft'):
            batch_op.add_column(
                sa.Column('is_draft', sa.Boolean(), nullable=False, default=False)
            )
        if not batch_op.columns.get('published_at'):
            batch_op.add_column(
                sa.Column('published_at', sa.DateTime(), nullable=True)
            )
    
    print("✅ Enterprise tables created successfully")


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_job_telemetry_created', 'job_telemetry')
    op.drop_index('idx_job_telemetry_job_stage', 'job_telemetry')
    op.drop_index('idx_report_jobs_created', 'report_jobs')
    op.drop_index('idx_report_jobs_status_priority', 'report_jobs')
    op.drop_index('idx_report_jobs_user_status', 'report_jobs')
    
    # Drop tables
    op.drop_table('job_telemetry')
    op.drop_table('report_jobs')
    
    # Revert reports table modifications
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_column('published_at')
        batch_op.drop_column('is_draft')
        batch_op.drop_column('generation_model')
        batch_op.drop_column('job_id')
