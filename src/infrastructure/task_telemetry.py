"""
Task Telemetry — Celery signal handlers that persist every task execution
to the `task_runs` table.

Root cause this fixes (2026-07-12): scheduled tasks reported failures by
RETURNING strings like "Error: ..." — which went nowhere. distill_memories
AttributeError'd silently every night for weeks; the digest worker was never
scheduled at all and nobody noticed. task_runs makes every execution (and
every silent soft-failure) queryable, which the self-ops sentinel dimension
then watches via dead-man switches.

修復根因（2026-07-12）：排程任務用回傳字串 "Error: ..." 回報失敗——沒有任何
人讀。task_runs 讓每次執行（含靜默軟失敗）都可查詢,self-ops sentinel 維度
再據此做 dead-man 監控。

Design notes:
- Fire-and-forget: telemetry failure must NEVER break or slow a task.
- Raw parameterized SQL (規範九/十), no ORM.
- "soft_fail": task completed without raising, but returned a string
  matching ^Error — the legacy failure convention this module exists to
  surface. New code should raise instead.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SOFT_FAIL_RE = re.compile(r"^\s*error\b", re.IGNORECASE)

# task_id -> monotonic start time. Celery prerun/postrun run in the same
# worker process, so a module-level dict is safe (keys removed on postrun).
_task_start_times: Dict[str, float] = {}

_DDL = """
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
CREATE INDEX IF NOT EXISTS idx_task_runs_name_time ON task_runs (task_name, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_runs_status_time ON task_runs (status, finished_at DESC);
"""


def _record_run(
    task_name: str,
    task_id: Optional[str],
    status: str,
    error_class: Optional[str] = None,
    error_snippet: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """Persist one task execution. Swallows every exception by design."""
    try:
        from sqlalchemy import text
        from src.data.database import get_db_engine

        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO task_runs
                        (task_name, task_id, status, error_class, error_snippet, duration_ms)
                    VALUES
                        (:task_name, :task_id, :status, :error_class, :error_snippet, :duration_ms)
                """),
                {
                    "task_name": task_name,
                    "task_id": task_id,
                    "status": status,
                    "error_class": error_class,
                    "error_snippet": (error_snippet or "")[:500] or None,
                    "duration_ms": duration_ms,
                },
            )
            conn.commit()
    except Exception as exc:  # pragma: no cover - defensive by contract
        logger.debug("task_runs telemetry write failed (non-blocking): %s", exc)


def _on_task_prerun(task_id=None, task=None, **kwargs) -> None:
    if task_id:
        _task_start_times[task_id] = time.monotonic()
    # Session hygiene at task boundary — REMOVED 2026-08-02, no longer needed.
    #
    # Kept as an incident record: repositories used to share one
    # scoped_session registry per engine, so a task that died mid-transaction
    # left the thread-local session broken and the NEXT task on that worker
    # inherited it. send_event_digest failed hourly with
    # "psycopg2.InterfaceError: cursor already closed" exactly this way, and
    # this hook discarded the registry at task start to paper over it.
    #
    # The registry is gone (see src/data/database.py): each repository
    # instance now owns its session, and a task's repositories die with the
    # task, so there is nothing left to inherit.
    # 2026-08-02 移除：全域 registry 已刪除，session 隨 repository 實例消亡，
    # 沒有東西可被下一個 task 繼承。此註解保留作為當時事故的紀錄。


def _on_task_postrun(task_id=None, task=None, retval=None, state=None, **kwargs) -> None:
    started = _task_start_times.pop(task_id, None) if task_id else None
    duration_ms = (time.monotonic() - started) * 1000 if started else None
    task_name = getattr(task, "name", "unknown")

    # Celery marks the run SUCCESS even when the task returned "Error: ..."
    # (the legacy convention). Surface those as soft_fail.
    if state == "SUCCESS" and isinstance(retval, str) and _SOFT_FAIL_RE.match(retval):
        _record_run(
            task_name, task_id, "soft_fail",
            error_class="SoftFailReturn",
            error_snippet=retval,
            duration_ms=duration_ms,
        )
        return

    if state == "SUCCESS":
        _record_run(task_name, task_id, "success", duration_ms=duration_ms)
    # FAILURE state is handled by _on_task_failure (has the real exception).


def _on_task_failure(task_id=None, exception=None, sender=None, **kwargs) -> None:
    started = _task_start_times.pop(task_id, None) if task_id else None
    duration_ms = (time.monotonic() - started) * 1000 if started else None
    _record_run(
        getattr(sender, "name", "unknown"),
        task_id,
        "failure",
        error_class=type(exception).__name__ if exception else None,
        error_snippet=str(exception) if exception else None,
        duration_ms=duration_ms,
    )


def register_task_telemetry() -> None:
    """Connect Celery signals. Called once from celery_app.py."""
    from celery.signals import task_prerun, task_postrun, task_failure

    task_prerun.connect(_on_task_prerun, weak=False)
    task_postrun.connect(_on_task_postrun, weak=False)
    task_failure.connect(_on_task_failure, weak=False)
    logger.info("Task telemetry registered (task_runs harvesting active)")
