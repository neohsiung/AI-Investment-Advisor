"""023_agent_cognitive_blindspots: A2 Cognitive Blindspot Detection and Self-Reflection Memory

Revision ID: 023_agent_cognitive_blindspots
Revises: 022_add_generated_code_artifacts
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "023_agent_cognitive_blindspots"
down_revision = "022_add_generated_code_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_cognitive_blindspots (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            agent_name VARCHAR(64) NOT NULL,
            bias_pattern VARCHAR(50) NOT NULL,
            regime VARCHAR(50) NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 2,
            avg_alpha_loss NUMERIC(10, 4) DEFAULT 0.0,
            severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
            corrective_guidance TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            detected_at TIMESTAMPTZ DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_agent_blindspots_user_agent_active 
            ON agent_cognitive_blindspots (user_id, agent_name, is_active);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS agent_cognitive_blindspots CASCADE;")
