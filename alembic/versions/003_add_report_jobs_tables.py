"""Add report_jobs and job_telemetry tables for enterprise architecture

Revision ID: 003_add_report_jobs_tables
Revises: 002_xxx
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003_add_report_jobs_tables'
down_revision = 'merge_heads_001'
branch_labels = None
depends_on = None


def upgrade():
    """Create new tables for enterprise job queue architecture."""
    
    # Create report_jobs table
    op.create_table(
        'report_jobs',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('report_type', sa.Text(), nullable=False),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        
        # Job Status
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('current_stage', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='50'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), 
                 nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        
        # Failure Info
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(), nullable=True),
        
        # Output References
        sa.Column('report_id', sa.Text(), nullable=True),
        
        # Checkpointing
        sa.Column('checkpoint_data', postgresql.JSONB(), nullable=True),
        sa.Column('last_checkpoint_stage', sa.Integer(), nullable=True),
        
        # Metadata
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('cost_estimate', sa.Float(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        
        # Primary Key
        sa.PrimaryKeyConstraint('id'),
        
        # Foreign Keys
        sa.ForeignKeyConstraint(['user_id'], ['settings.user_id']),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id']),
    )
    
    # Indexes for report_jobs
    op.create_index('idx_report_jobs_user_status', 'report_jobs', 
                   ['user_id', 'status'], unique=False)
    op.create_index('idx_report_jobs_scheduled_date', 'report_jobs', 
                   ['scheduled_date'], unique=False)
    op.create_index('idx_report_jobs_created_at', 'report_jobs', 
                   ['created_at'], unique=False)
    op.create_index('idx_report_jobs_priority', 'report_jobs', 
                   ['priority', 'created_at'], unique=False)
    
    
    # Create job_telemetry table
    op.create_table(
        'job_telemetry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Text(), nullable=False),
        sa.Column('stage', sa.Integer(), nullable=False),
        sa.Column('stage_name', sa.Text(), nullable=True),
        
        # Timing
        sa.Column('started_at', sa.DateTime(timezone=True), 
                 nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        
        # Metrics
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        
        # Error Tracking
        sa.Column('error_code', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        
        # Context
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        
        # Primary Key
        sa.PrimaryKeyConstraint('id'),
        
        # Foreign Key
        sa.ForeignKeyConstraint(['job_id'], ['report_jobs.id']),
    )
    
    # Indexes for job_telemetry
    op.create_index('idx_job_telemetry_job_stage', 'job_telemetry', 
                   ['job_id', 'stage'], unique=False)
    op.create_index('idx_job_telemetry_completed_at', 'job_telemetry', 
                   ['completed_at'], unique=False)
    op.create_index('idx_job_telemetry_stage_name', 'job_telemetry', 
                   ['stage_name'], unique=False)
    
    
    # Modify reports table to add new columns
    op.add_column('reports', sa.Column('job_id', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('generation_model', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('generation_cost_usd', sa.Float(), nullable=True))
    op.add_column('reports', sa.Column('is_draft', sa.Boolean(), nullable=False, 
                                       server_default=sa.false()))
    
    # Add foreign key constraint for reports.job_id
    op.create_foreign_key('fk_reports_job_id', 'reports', 'report_jobs',
                         ['job_id'], ['id'])
    
    # Add indexes for reports modifications
    op.create_index('idx_reports_job_id', 'reports', ['job_id'], unique=False)
    op.create_index('idx_reports_generation_model', 'reports', 
                   ['generation_model'], unique=False)


def downgrade():
    """Revert the schema changes."""
    
    # Drop indexes
    op.drop_index('idx_reports_generation_model', table_name='reports')
    op.drop_index('idx_reports_job_id', table_name='reports')
    
    # Drop foreign key from reports
    op.drop_constraint('fk_reports_job_id', 'reports', type_='foreignkey')
    
    # Drop columns from reports
    op.drop_column('reports', 'is_draft')
    op.drop_column('reports', 'generation_cost_usd')
    op.drop_column('reports', 'generation_model')
    op.drop_column('reports', 'job_id')
    
    # Drop job_telemetry indexes and table
    op.drop_index('idx_job_telemetry_stage_name', table_name='job_telemetry')
    op.drop_index('idx_job_telemetry_completed_at', table_name='job_telemetry')
    op.drop_index('idx_job_telemetry_job_stage', table_name='job_telemetry')
    op.drop_table('job_telemetry')
    
    # Drop report_jobs indexes and table
    op.drop_index('idx_report_jobs_priority', table_name='report_jobs')
    op.drop_index('idx_report_jobs_created_at', table_name='report_jobs')
    op.drop_index('idx_report_jobs_scheduled_date', table_name='report_jobs')
    op.drop_index('idx_report_jobs_user_status', table_name='report_jobs')
    op.drop_table('report_jobs')
