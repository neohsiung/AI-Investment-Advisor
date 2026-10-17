"""027_trade_proposals: proposal ledger + counterfactual columns on decision_outcomes

Revision ID: 027_trade_proposals
Revises: 026_strategy_trials
Create Date: 2026-10-17
"""
from alembic import op

revision = "027_trade_proposals"
down_revision = "026_strategy_trials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS trade_proposals (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            source VARCHAR(16) NOT NULL,
            strategy_id VARCHAR,
            ticker VARCHAR NOT NULL,
            direction VARCHAR(4) NOT NULL,
            rationale_text TEXT,
            evidence TEXT,
            llm_model VARCHAR,
            mode VARCHAR(8) NOT NULL DEFAULT 'shadow',
            status VARCHAR(16) NOT NULL DEFAULT 'proposed',
            reject_reason TEXT,
            sized_amount_usd NUMERIC(18, 4),
            validator_version VARCHAR(32),
            idempotency_key VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_trade_proposals_source
                CHECK (source IN ('event', 'strategy', 'rotation', 'parking', 'manual', 'safety')),
            CONSTRAINT ck_trade_proposals_direction CHECK (direction IN ('BUY', 'SELL')),
            CONSTRAINT ck_trade_proposals_mode CHECK (mode IN ('shadow', 'enforce')),
            CONSTRAINT ck_trade_proposals_status
                CHECK (status IN ('proposed', 'rejected', 'approved', 'submitting',
                                  'executed', 'exec_failed', 'expired')),
            CONSTRAINT uq_trade_proposals_idempotency
                UNIQUE (user_id, source, ticker, direction, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_trade_proposals_user_created
            ON trade_proposals (user_id, created_at);

        ALTER TABLE decision_outcomes ADD COLUMN IF NOT EXISTS proposal_id VARCHAR;
        ALTER TABLE decision_outcomes ADD COLUMN IF NOT EXISTS strategy_id VARCHAR;
        ALTER TABLE decision_outcomes ADD COLUMN IF NOT EXISTS source VARCHAR;
        ALTER TABLE decision_outcomes
            ADD COLUMN IF NOT EXISTS is_counterfactual BOOLEAN NOT NULL DEFAULT FALSE;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE decision_outcomes DROP COLUMN IF EXISTS is_counterfactual;
        ALTER TABLE decision_outcomes DROP COLUMN IF EXISTS source;
        ALTER TABLE decision_outcomes DROP COLUMN IF EXISTS strategy_id;
        ALTER TABLE decision_outcomes DROP COLUMN IF EXISTS proposal_id;
        DROP TABLE IF EXISTS trade_proposals;
    """)
