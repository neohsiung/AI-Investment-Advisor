"""remediation_log: tiered self-healing action history (Loop 2, B-P2.3)

2026-07-14: self_ops_service.py (B-P0.2) already DETECTS repeat failures
(>=3 same error_class in 24h) but only ever emits an alert — nothing acts
on it. This table backs a tiered response: T1 (auto re-enqueue the task,
capped at 2 attempts before escalating), T2 (advanced-tier diagnosis via
LLM, never auto-applied), T3 (Telegram page with the diagnosis attached).
Tracks attempts so repeated T1s don't loop forever on a task that's
genuinely broken (not transient).

2026-07-14：self_ops_service.py（B-P0.2）已經能偵測重複失敗（24h內同
error_class ≥3次）但只會發告警,沒有任何動作。此表支撐分級回應：T1（自動
重排任務,上限2次後升級）、T2（進階模型診斷,絕不自動套用）、T3（Telegram
呼人並附診斷）。追蹤嘗試次數,避免對真正壞掉（非暫時性）的任務無限重排。

Revision ID: 016_remediation_log
Revises: 015_user_preferences
Create Date: 2026-07-14
"""
from alembic import op

revision = "016_remediation_log"
down_revision = "015_user_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS remediation_log (
            id BIGSERIAL PRIMARY KEY,
            task_name TEXT NOT NULL,
            error_class TEXT NOT NULL,
            tier TEXT NOT NULL CHECK (tier IN ('T1', 'T2', 'T3')),
            action_taken TEXT NOT NULL,
            diagnosis TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_remediation_log_lookup
        ON remediation_log (task_name, error_class, created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS remediation_log;")
