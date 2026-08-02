"""agent_rules: per-user Postgres storage for distilled General Rules (Loop 1)

2026-07-14: AgentState.load_general_rules/save_general_rules previously
stored the ONLY copy of each agent's distilled rules in
workspace/{agent}/STATE.md, keyed purely by agent_name — no user_id at
all, meaning rules were effectively global across every tenant. Postgres
becomes the source of truth; STATE.md is now written as a render cache
only (kept for the WAL-flush collision fix already in wal_protocol.py /
three_tier_memory.py). No backfill needed — every STATE.md file's
"## General Rules" section was still empty/absent at migration time
(confirmed by inspection, no _distill_failure had fired against real data
yet).

2026-07-14：AgentState 原本只把每個 agent 的蒸餾規則存在
workspace/{agent}/STATE.md，僅以 agent_name 為鍵——完全沒有 user_id，等於
規則在所有租戶間是全域共享的。改為 Postgres 為 source of truth，STATE.md
降級為 render cache（沿用既有的 WAL flush 碰撞修正機制）。無需 backfill
——遷移時每個 STATE.md 的 "## General Rules" 區段都仍是空的/不存在
（已檢查確認，尚無 _distill_failure 對真實資料寫入過）。

Revision ID: 012_agent_rules
Revises: 011_expected_outcomes
Create Date: 2026-07-14
"""
from alembic import op

revision = "012_agent_rules"
down_revision = "011_expected_outcomes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_rules (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            rule_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded')),
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # At most one 'active' rule-set per (user, agent) — save_general_rules
    # supersedes the previous active row rather than overwriting in place,
    # preserving history for future rule-lifecycle work (B-P2).
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_rules_active
        ON agent_rules (user_id, agent_name) WHERE status = 'active';
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_rules_lookup
        ON agent_rules (user_id, agent_name, status);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS agent_rules;")
