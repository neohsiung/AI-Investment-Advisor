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
    # report_jobs and job_telemetry were already created by 003_add_report_jobs_tables.
    # This migration only adds published_at to reports (the one column 003 omits).
    bind = op.get_bind()
    cols = [row[0] for row in bind.execute(
        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='reports'")
    )]
    if 'published_at' not in cols:
        op.add_column('reports', sa.Column('published_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'published_at')
