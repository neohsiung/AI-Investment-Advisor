"""agent_rules lifecycle columns + rule_citations (Loop 1 — B-P2.1)

2026-07-14: B-P1.1 introduced agent_rules but modeled it as ONE growing
blob row per (user_id, agent_name) — every distilled rule got appended
into a single rule_text string. That precluded per-rule citation
tracking, scoring, dedup, and expiry (the whole point of this phase),
since there was no way to reference an individual rule. Drops the
"one active row per agent" uniqueness constraint (multiple atomic active
rules per agent are now expected) and adds the columns needed for
lifecycle management: score (EWMA of cited-decision alpha), times_cited,
expires_at, embedding (dedup via pgvector cosine), source_decision_id.

2026-07-14：B-P1.1 把 agent_rules 建模成「每個 (user,agent) 一顆持續長大的
部落格 row」——每條蒸餾規則都被串接進同一個 rule_text 字串。這樣無法做
per-rule 引用追蹤、計分、去重、過期（正是這個階段的目的），因為沒有辦法
指向單一規則。移除「每 agent 僅一顆 active row」的唯一約束（現在預期每個
agent 可有多顆獨立 active 規則），並加上生命週期管理所需欄位。

Revision ID: 014_rule_lifecycle
Revises: 013_interaction_feedback
Create Date: 2026-07-14
"""
from alembic import op

revision = "014_rule_lifecycle"
down_revision = "013_interaction_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS uq_agent_rules_active;")
    op.execute("""
        ALTER TABLE agent_rules
            ADD COLUMN IF NOT EXISTS score DOUBLE PRECISION NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS times_cited INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS embedding vector(768),
            ADD COLUMN IF NOT EXISTS source_decision_id TEXT;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_rules_active_lookup
        ON agent_rules (user_id, agent_name, status);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS rule_citations (
            id BIGSERIAL PRIMARY KEY,
            rule_id BIGINT NOT NULL REFERENCES agent_rules(id) ON DELETE CASCADE,
            decision_id TEXT NOT NULL,
            applied BOOLEAN NOT NULL DEFAULT TRUE,
            alpha_pct DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rule_citations_rule ON rule_citations (rule_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rule_citations_decision ON rule_citations (decision_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS rule_citations;")
    op.execute("""
        ALTER TABLE agent_rules
            DROP COLUMN IF EXISTS score,
            DROP COLUMN IF EXISTS times_cited,
            DROP COLUMN IF EXISTS expires_at,
            DROP COLUMN IF EXISTS embedding,
            DROP COLUMN IF EXISTS source_decision_id;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_rules_active
        ON agent_rules (user_id, agent_name) WHERE status = 'active';
    """)
