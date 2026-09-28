"""022_add_generated_code_artifacts: autonomous code synthesis, AST audits, and canary status

Revision ID: 022_add_generated_code_artifacts
Revises: 021_backfill_integrity_checks
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "022_add_generated_code_artifacts"
down_revision = "021_backfill_integrity_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS generated_code_artifacts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            source_code TEXT NOT NULL,
            test_code TEXT,
            ast_hash VARCHAR(64) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            parameters JSONB DEFAULT '{}'::jsonb,
            backtest_metrics JSONB DEFAULT '{}'::jsonb,
            ast_metrics JSONB DEFAULT '{}'::jsonb,
            shadow_days_remaining INTEGER DEFAULT 14,
            shadow_tracking_log JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_gen_code_user_status ON generated_code_artifacts (user_id, status);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS generated_code_artifacts CASCADE;")
