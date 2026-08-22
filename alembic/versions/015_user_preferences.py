"""user_preferences: learned risk appetite + sector aversions (Loop 3, B-P2.2)

2026-07-14: interaction_feedback (B-P1.3) captures WHY a user rejected a
trade but nothing aggregates it into an actionable preference profile.
This table holds the weekly-computed summary: a risk-appetite score, a
JSON map of sector -> reasoned-rejection count, a position-size-comfort
signal, and a short prose summary injected into council prompts (same
pattern as agent_rules' General Rules injection).

Also adds interaction_feedback.ticker — captured from the approval
request's payload so rejections can be attributed to a sector.

2026-07-14：interaction_feedback（B-P1.3）捕捉了「為什麼拒絕」但沒有任何
機制把它彙整成可用的偏好檔案。此表存每週計算的摘要：風險胃納分數、板塊
→有理由拒絕次數的 JSON 映射、部位大小舒適度訊號、以及注入評議 prompt 的
短 prose 摘要（跟 agent_rules 的 General Rules 注入同一模式）。

Revision ID: 015_user_preferences
Revises: 014_rule_lifecycle
Create Date: 2026-07-14
"""
from alembic import op

revision = "015_user_preferences"
down_revision = "014_rule_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE interaction_feedback ADD COLUMN IF NOT EXISTS ticker TEXT;")
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            risk_appetite_score DOUBLE PRECISION,
            sector_aversions JSONB NOT NULL DEFAULT '{}'::jsonb,
            position_comfort DOUBLE PRECISION,
            summary_text TEXT,
            sample_size INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS user_preferences;")
    op.execute("ALTER TABLE interaction_feedback DROP COLUMN IF EXISTS ticker;")
