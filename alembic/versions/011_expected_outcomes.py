"""expected_outcomes: dead-man switches for the self-ops sentinel (Loop 2)

2026-07-12: every incident this week shared one root cause — expected
periodic outcomes silently stopped happening and nothing watched for their
absence (digest worker never scheduled, distill_memories failing nightly,
risk_keywords empty for months). This table declares "X should happen at
least every N seconds"; SelfOpsService checks it every 15 minutes against
task_runs and named SQL checks, alerting on breaches.

2026-07-12：本週事故共同根因——「預期會發生的週期性結果」靜默停止且無人監
控其缺席。此表宣告「X 至少每 N 秒應發生一次」,SelfOpsService 每 15 分鐘
對照 task_runs 與具名 SQL 檢查,違約即告警。

Revision ID: 011_expected_outcomes
Revises: 010_task_runs
Create Date: 2026-07-12
"""
from alembic import op

revision = "011_expected_outcomes"
down_revision = "010_task_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS expected_outcomes (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('task_success', 'named_check')),
            target TEXT NOT NULL,
            max_gap_seconds INTEGER NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_ok_at TIMESTAMPTZ,
            last_alerted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS expected_outcomes;")
