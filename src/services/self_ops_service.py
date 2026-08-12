"""
SelfOpsService — dead-man switches + config-drift detection (Loop 2).

Watches for the ABSENCE of expected periodic outcomes, the failure mode
behind every incident of 2026-07 week 2: the digest worker that was never
scheduled, distill_memories AttributeError-ing nightly, risk_keywords
sitting empty for months. Three checks, all pure SQL (zero LLM cost):

1. task_success dead-man:每個 beat task 應在 max_gap_seconds 內至少成功一次
   (expectations auto-derived from celery beat_schedule — which doubles as
   config-drift detection: a task scheduled but never appearing in
   task_runs, or an expectation whose task left the schedule, is drift).
2. named_check: business-level invariants (risk_keywords non-empty,
   pending decisions not piling up) declared in _NAMED_CHECKS below —
   SQL lives in code, the table only references the key (no SQL-in-DB).
3. repeat-failure escalation: ≥3 soft_fail/failure of the same task in
   24h → alert even if a success eventually slipped through.

Alerts go to event_queue (P1 → carried by the hourly digest) and, for
critical breaches, directly to notification channels. Re-alerts for the
same breach are suppressed for ALERT_COOLDOWN_HOURS.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_HOURS = 6

# Dispatcher → child task, for the fan-out divergence check below.
#
# 2026-08-10: the outage that motivated this check ran for three days without
# tripping a single dead-man switch. Expectations are derived from the beat
# schedule, and the beat schedule only ever names the *dispatchers*. The
# dispatchers kept succeeding — `.delay()` returns as soon as the message is
# queued — while Redis had hit `max number of clients reached`, so no worker
# ever consumed the children. Over the final two days: 95 successful
# `dispatch_sentinel_tick` runs, 2 successful `sentinel_tick` runs. Every
# monitored signal was green while the trading loop was dead.
#
# The names cannot be derived by convention: `dispatch_broker_sync` fans out
# to `sync_broker_positions`, not `broker_sync`. Hence an explicit map, kept
# honest by test_self_ops_dispatcher_divergence.py, which reads the actual
# `.delay()` call in each dispatcher's source and fails if this drifts.
#
# 2026-08-10：本次事故三天未觸發任何 dead-man 監控——期望值衍生自 beat 排程，
# 而排程只列出 dispatcher。dispatcher 一路成功（.delay() 送出即返回），但 Redis
# 已達連線上限，子任務從未被消費。最後兩天：dispatch_sentinel_tick 成功 95 次，
# sentinel_tick 僅 2 次，所有監控訊號全綠而交易迴圈已死。
# 名稱無法由命名慣例推導（dispatch_broker_sync 對應 sync_broker_positions），
# 故採顯式對照表，並由測試比對 dispatcher 原始碼中的 .delay() 呼叫防止漂移。
_TASK_PREFIX = "src.infrastructure.tasks."
DISPATCHER_CHILD_TASKS: Dict[str, str] = {
    "dispatch_market_intelligence": "generate_market_intelligence",
    "dispatch_sentinel_tick": "sentinel_tick",
    "dispatch_broker_sync": "sync_broker_positions",
    "dispatch_memory_distill": "distill_memories",
    "dispatch_experience_replay": "experience_replay",
    "dispatch_keyword_refine": "keyword_refine",
    "dispatch_rule_curation": "curate_agent_rules",
    "dispatch_user_preferences": "update_user_preferences",
    "dispatch_weekly_validation": "weekly_validation",
    "dispatch_event_digest": "send_event_digest",
    "dispatch_daily_report": "generate_daily_report",
}

# How far back to compare dispatcher and child success counts.
# 比對 dispatcher 與子任務成功次數的回看窗口。
DIVERGENCE_WINDOW_MINUTES = 60

# Dispatchers must have run at least this many times in the window before a
# zero child count means anything — otherwise an infrequent dispatcher (daily
# report, weekly validation) reads as a breach every time it is idle.
# dispatcher 在窗口內至少要跑過這麼多次，子任務為 0 才有意義；否則低頻的
# dispatcher（每日報表、每週驗證）在閒置時都會被誤判為異常。
DIVERGENCE_MIN_DISPATCHES = 3

# Business invariants checked by key. SQL stays in code (規範十: no SQL in
# data). Each returns (ok: bool, detail: str).
_NAMED_CHECKS: Dict[str, Dict[str, Any]] = {
    "risk_keywords_nonempty": {
        "sql": "SELECT COUNT(*) FROM risk_keywords",
        "ok_when": lambda count: count > 0,
        "detail": "risk_keywords row count",
        "critical": True,  # empty table disabled an entire sentinel dimension for months
    },
    "decision_outcomes_not_stuck": {
        # A decision is pending while resolved_at IS NULL; it is only "stuck"
        # once its horizon has elapsed by 5+ days and resolve_pending still
        # hasn't picked it up.
        "sql": """
            SELECT COUNT(*) FROM decision_outcomes
            WHERE resolved_at IS NULL
              AND decided_at < NOW() - (horizon_days + 5) * INTERVAL '1 day'
        """,
        "ok_when": lambda count: count == 0,
        "detail": "decisions past horizon+5d still unresolved",
        "critical": False,
    },
}


def derive_max_gap_seconds(schedule) -> int:
    """
    Derive a worst-case-plus-grace gap from a celery crontab schedule.
    Deterministic string inspection of the original crontab fields —
    intentionally coarse (dead-man thresholds, not precision scheduling).
    """
    minute = str(getattr(schedule, "_orig_minute", "*"))
    hour = str(getattr(schedule, "_orig_hour", "*"))
    dow = str(getattr(schedule, "_orig_day_of_week", "*"))
    dom = str(getattr(schedule, "_orig_day_of_month", "*"))

    if dom != "*":
        return 32 * 86400                      # monthly
    if dow != "*":
        if "-" in dow or "," in dow:
            return 74 * 3600                   # weekday sets: worst gap = weekend (Fri→Mon)
        return 8 * 86400                       # single weekly day
    if hour != "*":
        return 26 * 3600                       # daily at fixed hour
    if minute.startswith("*/"):
        try:
            n = int(minute[2:])
            return max(n * 60 * 2 + 300, 900)  # every N minutes
        except ValueError:
            return 3600
    if minute == "*":
        return 300                             # every minute → alert after 5min silence
    return 2 * 3600 + 1800                     # fixed minute, every hour


class SelfOpsService:
    """Dead-man switch evaluation. All methods are synchronous, pure SQL."""

    def __init__(self, user_id: Optional[str] = None):
        # Alerts are ops-level: they go to the deployment admin/primary user.
        import os
        self.user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
        if not self.user_id:
            from src.repositories.user_repository import AlchemyUserRepository
            self.user_id = AlchemyUserRepository().get_first_user_id()

    def _engine(self):
        from src.data.database import get_db_engine
        return get_db_engine()

    # ── Expectation sync (also config-drift detection) ──────────────────

    def sync_beat_expectations(self) -> Dict[str, Any]:
        """
        Upsert one task_success expectation per celery beat entry.
        Expectations whose task vanished from the schedule are disabled and
        reported as drift.
        """
        from src.infrastructure.celery_app import app as celery_app

        scheduled: Dict[str, int] = {}
        for entry in celery_app.conf.beat_schedule.values():
            task_name = entry["task"]
            gap = derive_max_gap_seconds(entry["schedule"])
            # A task on several schedules (e.g. distill_memories daily+weekly)
            # is satisfied by its most frequent cadence.
            scheduled[task_name] = min(gap, scheduled.get(task_name, gap))

        # 2026-08-10: also expect the CHILD of every scheduled dispatcher.
        #
        # Watching only the beat entries is what let the Redis-exhaustion
        # outage run for three days unalarmed: the schedule names dispatchers,
        # a dispatcher's `.delay()` succeeds as soon as the broker accepts the
        # message, and no worker ever consumed the children. Registering the
        # children here puts them under the same dead-man switch, at the same
        # cadence, including the low-frequency ones (daily report, weekly
        # validation) that _check_dispatcher_divergence cannot judge because
        # they never reach its minimum count inside a one-hour window.
        #
        # 2026-08-10：僅監看 beat 項目正是事故三天未告警的原因——排程只列
        # dispatcher，而 .delay() 送出即成功。在此一併登記子任務，讓它們納入同一
        # 套 dead-man 監控，也涵蓋 _check_dispatcher_divergence 因一小時窗口內次數
        # 不足而無法判斷的低頻任務。
        expected_children: Dict[str, int] = {}
        for task_name, gap in scheduled.items():
            short = task_name.rsplit(".", 1)[-1]
            child = DISPATCHER_CHILD_TASKS.get(short)
            if child:
                child_task = f"{_TASK_PREFIX}{child}"
                expected_children[child_task] = min(
                    gap, expected_children.get(child_task, gap)
                )

        drift: List[str] = []
        with self._engine().connect() as conn:
            for task_name, gap in scheduled.items():
                conn.execute(
                    text("""
                        INSERT INTO expected_outcomes (name, kind, target, max_gap_seconds)
                        VALUES (:name, 'task_success', :target, :gap)
                        ON CONFLICT (name) DO UPDATE
                        SET max_gap_seconds = EXCLUDED.max_gap_seconds, enabled = TRUE
                    """),
                    {"name": f"beat:{task_name}", "target": task_name, "gap": gap},
                )
            for child_task, gap in expected_children.items():
                conn.execute(
                    text("""
                        INSERT INTO expected_outcomes (name, kind, target, max_gap_seconds)
                        VALUES (:name, 'task_success', :target, :gap)
                        ON CONFLICT (name) DO UPDATE
                        SET max_gap_seconds = EXCLUDED.max_gap_seconds, enabled = TRUE
                    """),
                    {"name": f"child:{child_task}", "target": child_task, "gap": gap},
                )
            # Drift: expectations for tasks no longer in the schedule
            rows = conn.execute(
                text("""
                    SELECT name, target FROM expected_outcomes
                    WHERE kind = 'task_success' AND enabled = TRUE
                      AND (name LIKE 'beat:%' OR name LIKE 'child:%')
                """)
            ).fetchall()
            for name, target in rows:
                live = scheduled if name.startswith("beat:") else expected_children
                if target not in live:
                    conn.execute(
                        text("DELETE FROM expected_outcomes WHERE name = :n"),
                        {"n": name},
                    )
                    drift.append(target)
            # Seed named checks
            for key in _NAMED_CHECKS:
                conn.execute(
                    text("""
                        INSERT INTO expected_outcomes (name, kind, target, max_gap_seconds)
                        VALUES (:name, 'named_check', :target, 86400)
                        ON CONFLICT (name) DO NOTHING
                    """),
                    {"name": f"check:{key}", "target": key},
                )
            conn.commit()
        return {"synced": len(scheduled), "drift_disabled": drift}

    # ── Evaluation ───────────────────────────────────────────────────────

    def check_all(self) -> Dict[str, Any]:
        """Evaluate all enabled expectations. Returns breach summary."""
        breaches: List[Dict[str, Any]] = []
        with self._engine().connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, name, kind, target, max_gap_seconds, last_alerted_at
                    FROM expected_outcomes WHERE enabled = TRUE
                """)
            ).fetchall()

            for row in rows:
                exp_id, name, kind, target, max_gap, last_alerted = row
                if kind == "task_success":
                    breach = self._check_task_success(conn, name, target, max_gap)
                else:
                    breach = self._check_named(conn, name, target)
                if breach is None:
                    conn.execute(
                        text("UPDATE expected_outcomes SET last_ok_at = NOW() WHERE id = :i"),
                        {"i": exp_id},
                    )
                    continue
                # Alert-cooldown suppression
                if last_alerted is not None:
                    age_h = (datetime.now(timezone.utc) - last_alerted).total_seconds() / 3600
                    if age_h < ALERT_COOLDOWN_HOURS:
                        continue
                conn.execute(
                    text("UPDATE expected_outcomes SET last_alerted_at = NOW() WHERE id = :i"),
                    {"i": exp_id},
                )
                breaches.append(breach)

            repeat = self._check_repeat_failures(conn)
            divergence = self._check_dispatcher_divergence(conn)
            conn.commit()

        breaches.extend(repeat)
        breaches.extend(divergence)
        if breaches:
            self._emit_alerts(breaches)
        return {"checked": True, "breaches": breaches}

    def _check_task_success(self, conn, name: str, task_name: str, max_gap: int) -> Optional[Dict]:
        row = conn.execute(
            text("""
                SELECT MAX(finished_at) FROM task_runs
                WHERE task_name = :t AND status = 'success'
            """),
            {"t": task_name},
        ).fetchone()
        last_success = row[0] if row else None
        if last_success is None:
            # Grace: telemetry itself is new; only flag never-ran once telemetry
            # has been collecting longer than the expected gap.
            oldest = conn.execute(text("SELECT MIN(finished_at) FROM task_runs")).fetchone()[0]
            if oldest is None:
                return None
            telemetry_age = (datetime.now(timezone.utc) - oldest).total_seconds()
            if telemetry_age < max_gap:
                return None
            return {
                "name": name, "severity": "critical",
                "detail": f"task {task_name} scheduled but NEVER succeeded since telemetry began",
            }
        gap = (datetime.now(timezone.utc) - last_success).total_seconds()
        if gap > max_gap:
            return {
                "name": name, "severity": "warning",
                "detail": f"task {task_name} last succeeded {gap/3600:.1f}h ago (limit {max_gap/3600:.1f}h)",
            }
        return None

    def _check_named(self, conn, name: str, key: str) -> Optional[Dict]:
        spec = _NAMED_CHECKS.get(key)
        if spec is None:
            return {"name": name, "severity": "warning",
                    "detail": f"named check '{key}' referenced in DB but not defined in code (drift)"}
        value = conn.execute(text(spec["sql"])).fetchone()[0]
        if spec["ok_when"](value):
            return None
        return {
            "name": name,
            "severity": "critical" if spec.get("critical") else "warning",
            "detail": f"{spec['detail']}: got {value}",
        }

    def _check_repeat_failures(self, conn) -> List[Dict]:
        # error_class grouping added 2026-07-14 (B-P2.3) — the tiered
        # remediation dispatch keys playbooks off error_class, not just
        # task_name, so two different failure modes on the same task
        # (e.g. TIMEOUT vs AttributeError) escalate independently.
        rows = conn.execute(
            text("""
                SELECT task_name, error_class, COUNT(*) AS n, MAX(error_snippet) AS sample
                FROM task_runs
                WHERE status IN ('soft_fail', 'failure')
                  AND finished_at > NOW() - INTERVAL '24 hours'
                GROUP BY task_name, error_class
                HAVING COUNT(*) >= 3
            """)
        ).fetchall()
        breaches = []
        for task_name, error_class, n, sample in rows:
            error_class = error_class or "Unknown"
            remediation = self._remediate(task_name, error_class, sample or "")
            breaches.append({
                "name": f"repeat:{task_name}:{error_class}", "severity": "critical",
                "detail": f"{n} {error_class} failures in 24h — sample: {(sample or '')[:200]} | remediation: {remediation}",
            })
        return breaches

    def _check_dispatcher_divergence(self, conn) -> List[Dict]:
        """
        Catch fan-out that queues work nobody executes.
        偵測「派工成功但子任務沒被執行」的情況。

        A dispatcher's `.delay()` returns the moment the message is accepted
        by the broker, so the dispatcher records `success` whether or not any
        worker ever picks the child up. Every other check in this service
        watches dispatchers (they are what the beat schedule names), which is
        why the 2026-08-10 Redis exhaustion stayed invisible for three days.

        This compares successes of each dispatcher against successes of the
        child it fans out to, over the same window. The child normally runs at
        least once per dispatch per active user, so a healthy ratio is >= 1.
        Zero children against a busy dispatcher means the queue is not being
        drained — worker down, broker refusing connections, or the child task
        unregistered.

        dispatcher 的 .delay() 在 broker 接受訊息時就返回，無論是否有 worker
        取走子任務，都會記為 success。本服務其他檢查全部盯著 dispatcher（因為
        beat 排程只列出它們），這正是 2026-08-10 事故三天無人察覺的原因。
        """
        rows = conn.execute(
            text("""
                SELECT task_name, COUNT(*) AS n
                FROM task_runs
                WHERE status = 'success'
                  AND finished_at > NOW() - (:window_minutes * INTERVAL '1 minute')
                GROUP BY task_name
            """),
            {"window_minutes": DIVERGENCE_WINDOW_MINUTES},
        ).fetchall()

        counts = {name: n for name, n in rows}

        def _count(short_name: str) -> int:
            # task_runs stores fully-qualified names; tolerate either form.
            # task_runs 存的是完整名稱，兩種寫法都容忍。
            return counts.get(f"{_TASK_PREFIX}{short_name}", counts.get(short_name, 0))

        breaches = []
        for dispatcher, child in DISPATCHER_CHILD_TASKS.items():
            n_dispatch = _count(dispatcher)
            if n_dispatch < DIVERGENCE_MIN_DISPATCHES:
                continue
            n_child = _count(child)
            if n_child > 0:
                continue
            breaches.append({
                "name": f"divergence:{dispatcher}",
                "severity": "critical",
                "detail": (
                    f"{dispatcher} succeeded {n_dispatch}x in the last "
                    f"{DIVERGENCE_WINDOW_MINUTES}m but {child} never ran — "
                    f"queued work is not being consumed (check worker health "
                    f"and broker connectivity)"
                ),
            })
        return breaches

    # ── Tiered remediation (Loop 2d, B-P2.3) ─────────────────────────────

    T1_MAX_ATTEMPTS = 2

    def _remediate(self, task_name: str, error_class: str, error_sample: str) -> str:
        """
        T1 (auto re-enqueue, capped) -> T2 (advanced-tier diagnosis, never
        auto-applied) -> T3 (Telegram page with diagnosis attached).
        Returns a short description of the action actually taken.
        """
        try:
            with self._engine().connect() as conn:
                t1_count = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM remediation_log
                        WHERE task_name = :t AND error_class = :e AND tier = 'T1'
                          AND created_at > NOW() - INTERVAL '24 hours'
                    """),
                    {"t": task_name, "e": error_class},
                ).fetchone()[0]
                t2_done = conn.execute(
                    text("""
                        SELECT diagnosis FROM remediation_log
                        WHERE task_name = :t AND error_class = :e AND tier = 'T2'
                          AND created_at > NOW() - INTERVAL '24 hours'
                        ORDER BY created_at DESC LIMIT 1
                    """),
                    {"t": task_name, "e": error_class},
                ).fetchone()
        except Exception as e:
            logger.warning(f"self_ops: remediation history lookup failed for {task_name}: {e}")
            return "lookup failed, no action taken"

        if t1_count < self.T1_MAX_ATTEMPTS:
            return self._remediate_t1(task_name, error_class)
        if not t2_done:
            return self._remediate_t2(task_name, error_class, error_sample)
        return self._remediate_t3(task_name, error_class, t2_done[0])

    def _log_remediation(self, task_name: str, error_class: str, tier: str, action: str, diagnosis: Optional[str] = None) -> None:
        try:
            with self._engine().begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO remediation_log (task_name, error_class, tier, action_taken, diagnosis)
                        VALUES (:t, :e, :tier, :action, :diagnosis)
                    """),
                    {"t": task_name, "e": error_class, "tier": tier, "action": action, "diagnosis": diagnosis},
                )
        except Exception as e:
            logger.warning(f"self_ops: failed to log remediation for {task_name}: {e}")

    def _remediate_t1(self, task_name: str, error_class: str) -> str:
        """Re-enqueue the task once. Transient error classes (TIMEOUT,
        RATE_LIMIT, SERVER_ERROR, NETWORK_ERROR) are exactly what a retry
        is for; for non-transient ones it's a harmless no-op at worst —
        the failure will simply recur and this task's own counter will
        exhaust into T2 within T1_MAX_ATTEMPTS attempts."""
        action = "requeue skipped (no celery app)"
        try:
            from src.infrastructure.celery_app import app as celery_app
            celery_app.send_task(task_name, args=(self.user_id,))
            action = f"re-enqueued {task_name}"
        except Exception as e:
            action = f"re-enqueue failed: {e}"
        self._log_remediation(task_name, error_class, "T1", action)
        logger.warning(f"self_ops T1: {task_name} ({error_class}) -> {action}")
        return action

    def _remediate_t2(self, task_name: str, error_class: str, error_sample: str) -> str:
        """Advanced-tier diagnosis. Never auto-applied — recorded for a
        human (and surfaced at T3 if the failures continue)."""
        diagnosis = None
        try:
            diagnosis = self._run_diagnosis(task_name, error_class, error_sample)
        except Exception as e:
            diagnosis = f"diagnosis generation failed: {e}"
        action = "diagnosed (not auto-applied)"
        self._log_remediation(task_name, error_class, "T2", action, diagnosis=diagnosis)
        logger.warning(f"self_ops T2: {task_name} ({error_class}) diagnosed: {(diagnosis or '')[:200]}")
        return f"{action}: {(diagnosis or '')[:150]}"

    def _run_diagnosis(self, task_name: str, error_class: str, error_sample: str) -> str:
        import asyncio
        from src.infrastructure.llm.llm_config_chain import build_config_chain
        from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
        from src.domain.interfaces import Message

        chain = build_config_chain(self.user_id, "advanced")
        if not chain:
            return "no advanced-tier model configured"
        pipeline = ResilientLLMPipeline(
            config_chain=chain, user_id=self.user_id,
            agent_name="SelfOpsDiagnostician", tier="advanced",
        )
        prompt = (
            f"A scheduled task '{task_name}' has failed >=3 times in 24h with error class "
            f"'{error_class}'. A retry did not resolve it. Sample error:\n{error_sample[:1000]}\n\n"
            "In 2-3 sentences: likely root cause, and a concrete suggested fix "
            "(code change, config change, or external dependency issue). Be specific."
        )

        async def _run():
            resp, _ = await pipeline.execute([Message(role="user", content=prompt)], temperature=0.2, max_tokens=250)
            return resp

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as ex:
                return ex.submit(lambda: asyncio.run(_run())).result()
        except RuntimeError:
            return asyncio.run(_run())

    def _remediate_t3(self, task_name: str, error_class: str, prior_diagnosis: str) -> str:
        """Escalate to a human via Telegram, attaching the T2 diagnosis
        (recomputing it every cycle would waste an advanced-tier call for
        no new information)."""
        action = "paged human via notification"
        self._log_remediation(task_name, error_class, "T3", action, diagnosis=prior_diagnosis)
        try:
            import asyncio
            from src.services.settings_service import SettingsService
            from src.services.notification_service import NotificationService
            settings_svc = SettingsService(user_id=self.user_id)
            notif = NotificationService.create_with_settings(settings_service=settings_svc, user_id=self.user_id)
            coro = notif.notify_all(
                user_id=self.user_id,
                title=f"🚨 需要人工介入: {task_name}",
                content=(
                    f"任務 {task_name} 持續失敗（{error_class}），自動重排與診斷都無法解決。\n\n"
                    f"上次診斷：{prior_diagnosis}"
                ),
                category="self_ops",
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(coro)
                else:
                    loop.run_until_complete(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as e:
            logger.error(f"self_ops T3: paging failed for {task_name}: {e}")
            action = f"paging failed: {e}"
        logger.error(f"self_ops T3: {task_name} ({error_class}) escalated to human")
        return action

    # ── Cost anomaly detection (Loop 2c) ─────────────────────────────────

    WEEKLY_BUDGET_USD = 30.0

    def check_cost_anomaly(self) -> Dict[str, Any]:
        """
        Detect LLM cost anomalies from llm_usage_logs. Pure SQL.
        Two signals:
          1. Weekly projection: trailing-24h spend × 7 > WEEKLY_BUDGET_USD.
          2. Statistical spike: latest full day > mean + 2.5σ of prior daily
             totals (needs ≥4 prior days — skipped quietly until enough data).
        成本異常偵測：週投影超標或單日支出超過歷史 2.5σ。
        """
        breaches: List[Dict[str, Any]] = []
        with self._engine().connect() as conn:
            last_24h = conn.execute(text("""
                SELECT COALESCE(SUM(total_cost_usd), 0) FROM llm_usage_logs
                WHERE timestamp > NOW() - INTERVAL '24 hours'
            """)).fetchone()[0] or 0
            projected_week = float(last_24h) * 7
            if projected_week > self.WEEKLY_BUDGET_USD:
                breaches.append({
                    "name": "cost:weekly_projection", "severity": "critical",
                    "detail": (f"trailing-24h spend ${float(last_24h):.2f} projects to "
                               f"${projected_week:.2f}/week (budget ${self.WEEKLY_BUDGET_USD:.0f})"),
                })

            rows = conn.execute(text("""
                SELECT date_trunc('day', timestamp) AS d, SUM(total_cost_usd) AS c
                FROM llm_usage_logs
                WHERE timestamp > NOW() - INTERVAL '8 days'
                  AND timestamp < date_trunc('day', NOW())
                GROUP BY 1 ORDER BY 1
            """)).fetchall()
            daily = [float(r[1]) for r in rows]
            if len(daily) >= 5:
                *history, latest = daily
                mean = sum(history) / len(history)
                var = sum((x - mean) ** 2 for x in history) / len(history)
                sigma = var ** 0.5
                if sigma > 0 and latest > mean + 2.5 * sigma:
                    breaches.append({
                        "name": "cost:daily_spike", "severity": "warning",
                        "detail": (f"yesterday ${latest:.2f} vs prior mean ${mean:.2f} "
                                   f"(+{(latest - mean) / sigma:.1f}σ)"),
                    })

        if breaches:
            self._emit_alerts(breaches)
        return {"projected_week_usd": round(projected_week, 2), "breaches": breaches}

    # ── Alerting ─────────────────────────────────────────────────────────

    def _emit_alerts(self, breaches: List[Dict]) -> None:
        """All breaches → event_queue (P1, hourly digest); critical → direct notify."""
        try:
            from src.services.event_aggregator import EventAggregator
            from src.data.models import EventQueue
            aggregator = EventAggregator()
            for b in breaches:
                aggregator.ingest_event(
                    user_id=self.user_id,
                    event_type="self_ops_alert",
                    content={"source": "self_ops", "title": b["name"],
                             "summary": b["detail"], "severity": b["severity"]},
                    tier=EventQueue.TIER_P1,
                    priority=80,
                )
        except Exception as e:
            logger.error(f"self_ops: event ingest failed: {e}")

        critical = [b for b in breaches if b["severity"] == "critical"]
        if not critical:
            return
        try:
            import asyncio
            from src.services.settings_service import SettingsService
            from src.services.notification_service import NotificationService
            settings_svc = SettingsService(user_id=self.user_id)
            notif = NotificationService.create_with_settings(
                settings_service=settings_svc, user_id=self.user_id
            )
            lines = [f"• {b['name']}: {b['detail']}" for b in critical]
            coro = notif.notify_all(
                user_id=self.user_id,
                title=f"🛠️ Self-Ops 關鍵告警 ({len(critical)})",
                content="系統維運哨兵偵測到關鍵缺席/重複失敗：\n" + "\n".join(lines),
                category="ops",
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(coro)
                else:
                    loop.run_until_complete(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as e:
            logger.error(f"self_ops: critical notification failed: {e}")
