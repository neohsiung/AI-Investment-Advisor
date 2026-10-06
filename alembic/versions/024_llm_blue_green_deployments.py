"""024_llm_blue_green_deployments: Track blue-green shadow evaluations, canaries, and rollbacks for LLM tiers

Revision ID: 024_llm_blue_green_deployments
Revises: 023_agent_cognitive_blindspots
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "024_llm_blue_green_deployments"
down_revision = "023_agent_cognitive_blindspots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_blue_green_deployments (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            tier VARCHAR(20) NOT NULL,
            blue_model_id VARCHAR(64) NOT NULL,
            green_model_id VARCHAR(64) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'EVALUATING',
            benchmark_prompt TEXT,
            blue_latency_ms DOUBLE PRECISION,
            green_latency_ms DOUBLE PRECISION,
            blue_success_rate DOUBLE PRECISION DEFAULT 1.0,
            green_success_rate DOUBLE PRECISION DEFAULT 1.0,
            blue_cost_per_1k NUMERIC(12, 6) DEFAULT 0.0,
            green_cost_per_1k NUMERIC(12, 6) DEFAULT 0.0,
            cost_saving_pct DOUBLE PRECISION DEFAULT 0.0,
            evaluation_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            promoted_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_llm_bg_user_tier_status 
            ON llm_blue_green_deployments (user_id, tier, status);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_blue_green_deployments CASCADE;")
