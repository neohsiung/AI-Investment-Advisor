"""026_strategy_trials: every strategy variant ever evaluated (the multiple-testing ledger)

Revision ID: 026_strategy_trials
Revises: 025_llm_real_cost
Create Date: 2026-10-16
"""
from alembic import op

revision = "026_strategy_trials"
down_revision = "025_llm_real_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS strategy_trials (
            params_hash VARCHAR(64) PRIMARY KEY,
            family VARCHAR(64) NOT NULL,
            params_json TEXT NOT NULL,
            first_eval_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_eval_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            n_evals INTEGER NOT NULL DEFAULT 0,
            last_metrics TEXT,
            last_verdict TEXT,
            status VARCHAR(24) NOT NULL DEFAULT 'rejected'
        );
        CREATE INDEX IF NOT EXISTS ix_strategy_trials_family ON strategy_trials (family);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS strategy_trials;")
