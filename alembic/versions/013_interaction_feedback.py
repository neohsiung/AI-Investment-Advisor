"""interaction_feedback: structured rejection-reason capture (Loop 3)

2026-07-14: InteractionService's approve/reject flow only recorded a
binary APPROVED/REJECTED status — no signal about WHY a user rejected a
trade, so nothing could ever learn from it. This table captures a reason
code (one Telegram-button tap) or free text, and also logs the timeout
case (no response at all), per the approved self-improvement-loop plan
(Loop 3 — user-feedback-driven evolution).

2026-07-14：InteractionService 的核准/拒絕流程只記錄二元 APPROVED/REJECTED
狀態——完全沒有「為什麼拒絕」的訊號，系統無從學習。此表捕捉原因碼
（Telegram 按鈕一鍵選）或自由文字，也記錄逾時未回應的情況（Loop 3：用戶
回饋驅動進化）。

Revision ID: 013_interaction_feedback
Revises: 012_agent_rules
Create Date: 2026-07-14
"""
from alembic import op

revision = "013_interaction_feedback"
down_revision = "012_agent_rules"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS interaction_feedback (
            id BIGSERIAL PRIMARY KEY,
            request_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'expired')),
            reason_code TEXT,
            free_text TEXT,
            responded_in_s DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_interaction_feedback_user
        ON interaction_feedback (user_id, created_at DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_interaction_feedback_request
        ON interaction_feedback (request_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS interaction_feedback;")
