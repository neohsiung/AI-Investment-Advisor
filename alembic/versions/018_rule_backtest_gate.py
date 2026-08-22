"""018_rule_backtest_gate: rebuild status check constraint, add gating columns and partial index

Revision ID: 018_rule_backtest_gate
Revises: 017_product_events
Create Date: 2026-07-19
"""
from alembic import op

revision = "018_rule_backtest_gate"
down_revision = "017_product_events"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Rebuild status check constraint
    op.execute("ALTER TABLE agent_rules DROP CONSTRAINT IF EXISTS agent_rules_status_check;")
    op.execute("""
        ALTER TABLE agent_rules 
        ADD CONSTRAINT agent_rules_status_check 
        CHECK (status IN ('candidate', 'active', 'superseded', 'retired', 'rejected'));
    """)

    # 2. Add gating columns
    op.execute("""
        ALTER TABLE agent_rules
        ADD COLUMN IF NOT EXISTS gate_status TEXT,
        ADD COLUMN IF NOT EXISTS gate_checked_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS gate_details JSONB;
    """)

    # 3. Create partial index for candidate rules lookup
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_rules_candidate_lookup
        ON agent_rules (user_id) WHERE status = 'candidate';
    """)


def downgrade():
    # 1. Drop partial index
    op.execute("DROP INDEX IF EXISTS idx_agent_rules_candidate_lookup;")

    # 2. Drop columns
    op.execute("""
        ALTER TABLE agent_rules
        DROP COLUMN IF EXISTS gate_status,
        DROP COLUMN IF EXISTS gate_checked_at,
        DROP COLUMN IF EXISTS gate_details;
    """)

    # 3. Restore old status check constraint
    op.execute("ALTER TABLE agent_rules DROP CONSTRAINT IF EXISTS agent_rules_status_check;")
    op.execute("""
        ALTER TABLE agent_rules 
        ADD CONSTRAINT agent_rules_status_check 
        CHECK (status IN ('active', 'superseded'));
    """)
