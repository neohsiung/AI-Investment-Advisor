"""task_runs: Celery task execution telemetry (self-ops Loop 2)

2026-07-12: scheduled tasks reported failures by RETURNING "Error: ..."
strings that nobody read — distill_memories silently AttributeError'd
nightly, the digest worker was never even scheduled, risk_keywords inserts
failed for months. task_runs persists every Celery execution (success /
soft_fail / failure) so the self-ops sentinel dimension can watch cadence
and escalate repeats. Populated by src/infrastructure/task_telemetry.py.

2026-07-12：排程任務用回傳字串回報失敗,無人讀取。task_runs 持久化每次
Celery 執行,供 self-ops sentinel 維度監控節奏與升級重複失敗。

Revision ID: 010_task_runs
Revises: 009_risk_keywords_unique
Create Date: 2026-07-12
"""
from alembic import op

revision = "010_task_runs"
down_revision = "009_risk_keywords_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id BIGSERIAL PRIMARY KEY,
            task_name TEXT NOT NULL,
            task_id TEXT,
            status TEXT NOT NULL CHECK (status IN ('success', 'soft_fail', 'failure')),
            error_class TEXT,
            error_snippet TEXT,
            duration_ms DOUBLE PRECISION,
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_name_time ON task_runs (task_name, finished_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_status_time ON task_runs (status, finished_at DESC);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS task_runs;")
