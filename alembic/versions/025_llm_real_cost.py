"""025_llm_real_cost: real (LiteLLM-billed) LLM cost per day + collector state

Revision ID: 025_llm_real_cost
Revises: 024_llm_blue_green_deployments
Create Date: 2026-10-16
"""
from alembic import op

revision = "025_llm_real_cost"
down_revision = "024_llm_blue_green_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_real_cost_daily (
            day DATE NOT NULL,
            key_alias VARCHAR(64) NOT NULL,
            spend_usd NUMERIC(14, 6) NOT NULL DEFAULT 0,
            source VARCHAR(32) NOT NULL DEFAULT 'litellm_key_info',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (day, key_alias)
        );
        CREATE TABLE IF NOT EXISTS llm_real_cost_state (
            key_alias VARCHAR(64) PRIMARY KEY,
            last_spend NUMERIC(14, 6) NOT NULL,
            last_reset_at VARCHAR(40),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_real_cost_state; DROP TABLE IF EXISTS llm_real_cost_daily;")
