import os
import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)

# v2.1: Initialize Celery with Redis as the broker
# 使用 Redis 作為 Broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("investment_advisor", broker=redis_url, backend=redis_url)

app.config_from_object("src.infrastructure.celery_config", silent=True)

# Define Periodic Tasks (Celery Beat)
# 定義週期性任務（Celery Beat）

app.conf.beat_schedule = {
    "pre-market-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=8, minute=30),  # 08:30 AM EST
    },
    "mid-day-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=12, minute=0),   # 12:00 PM EST
    },
    "post-market-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=16, minute=30),  # 04:30 PM EST
    },
    "sentinel-minutely-tick": {
        "task": "src.infrastructure.tasks.dispatch_sentinel_tick",
        "schedule": crontab(minute="*"),           # Every minute
    },
    "broker-position-sync": {
        "task": "src.infrastructure.tasks.dispatch_broker_sync",
        "schedule": crontab(minute="*/5"),         # Every 5 minutes
    },
    "daily-memory-distillation": {
        "task": "src.infrastructure.tasks.dispatch_memory_distill",
        "schedule": crontab(hour=2, minute=0),     # 02:00 AM daily
    },
    # 2026-07-12: event_queue digest/housekeeping — previously lived only as
    # standalone scripts (report_digest_worker.py / event_housekeeper.py)
    # whose docstrings claimed a Hermes cron trigger that was never actually
    # registered, so non-P0 events (e.g. n8n RSS news) never reached the user.
    # Cadence is hourly per user decision (2026-07-12) — daily was this
    # session's initial assumption, not a documented product spec.
    "hourly-event-digest": {
        "task": "src.infrastructure.tasks.dispatch_event_digest",
        "schedule": crontab(minute=0),              # every hour on the hour
    },
    "daily-event-queue-housekeeping": {
        "task": "src.infrastructure.tasks.housekeep_event_queue",
        "schedule": crontab(hour=2, minute=15),    # 02:15 AM daily (offset from memory distillation)
    },
    # Self-ops Loop 2 (2026-07-12): dead-man switches over task_runs +
    # config-drift detection. Pure SQL, zero LLM.
    "self-ops-deadman-check": {
        "task": "src.infrastructure.tasks.self_ops_check",
        "schedule": crontab(minute="*/15"),        # every 15 minutes
    },
    "daily-cost-anomaly-check": {
        "task": "src.infrastructure.tasks.cost_anomaly_check",
        "schedule": crontab(hour=6, minute=30),    # 06:30 daily, after full prior day exists
    },
    # P2-2: daily_report — 每個交易日 17:00 執行 (盤後報告)
    "daily-report": {
        "task": "src.infrastructure.tasks.dispatch_daily_report",
        "schedule": crontab(hour=17, minute=0, day_of_week="1-5"),  # Mon-Fri 17:00 EST (after market close)
    },
    # "portfolio-rebalance-trigger" — REMOVED 2026-08-02.
    # It ran `crontab(minute="*/30", hour="8-16", day_of_week="1-5")` against
    # dispatch_portfolio_rebalance, whose body was byte-for-byte identical to
    # sentinel_tick's: `SentinelService(user_id).process_tick()`. But
    # process_tick() already runs Dimension 10 `_check_allocation_drift` and
    # 10.1 `_handle_rebalance_logic` unconditionally on EVERY minutely tick
    # (sentinel_service.py), so this entry added no coverage — it only made
    # process_tick run twice at :00 and :30. Both of those minutes satisfy the
    # `minute % 10 == 0` gate guarding the paid Tavily breaking-news search,
    # and :00 also hits the FRED macro branch, so it was doubling paid API and
    # LLM spend ~18×/trading day. `_handle_rebalance_logic`'s 30-minute
    # debounce could not stop it either: it keys off `self.last_fire_time` on
    # an instance that each Celery task constructs fresh.
    # Manual "rebalance now" still works — see tasks.trigger_portfolio_rebalance.
    # 2026-08-02 移除：與 sentinel_tick 呼叫同一個 process_tick()，而再平衡檢查本來
    # 每分鐘就會跑，此排程只造成 :00/:30 重複，且正好打在付費的 Tavily/FRED 分支上。
    "weekly-report-trigger": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=10, minute=0, day_of_week="6"),
    },
    "weekly-cost-review": {
        "task": "src.infrastructure.tasks.dispatch_memory_distill",
        "schedule": crontab(hour=22, minute=0, day_of_week="0"),
    },
    "monthly-report": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=9, minute=0, day_of_month="1"),
    },
    # P1-3: keyword_refine — 每週一 07:00 執行
    "weekly-keyword-refine": {
        "task": "src.infrastructure.tasks.dispatch_keyword_refine",
        "schedule": crontab(hour=7, minute=0, day_of_week="1"),  # Mon 07:00
    },
    # B-P2.1 (2026-07-14): weekly agent_rules curation — dedup + expiry.
    "weekly-rule-curation": {
        "task": "src.infrastructure.tasks.dispatch_rule_curation",
        "schedule": crontab(hour=6, minute=30, day_of_week="1"),  # Mon 06:30 (before keyword_refine)
    },
    # B-P2.2 (2026-07-14): weekly user-preference profile update.
    "weekly-user-preferences": {
        "task": "src.infrastructure.tasks.dispatch_user_preferences",
        "schedule": crontab(hour=6, minute=45, day_of_week="1"),  # Mon 06:45
    },
    # P1-4: experience_replay — 每週日 08:00 執行 (週日盤前復盤)
    "weekly-experience-replay": {
        "task": "src.infrastructure.tasks.dispatch_experience_replay",
        "schedule": crontab(hour=8, minute=0, day_of_week="0"),  # Sun 08:00
    },
    # P1-5: weekly_validation — 每週日 09:00 執行 (週日盤前回測驗證)
    "weekly-validation": {
        "task": "src.infrastructure.tasks.dispatch_weekly_validation",
        "schedule": crontab(hour=9, minute=0, day_of_week="0"),  # Sun 09:00
    },
}

app.conf.timezone = "America/New_York"


@worker_process_init.connect
def setup_db_worker_context(**kwargs):
    """
    Ensure each worker process has a clean database engine and is flagged
    to use NullPool to avoid connection sharing across forks.
    確保每個 worker process 有乾淨的資料庫引擎。
    """
    logger.info("Initializing Celery Worker Process: Setting IS_CELERY_WORKER=true")
    os.environ["IS_CELERY_WORKER"] = "true"

    # Force reload of engine if it was already initialized in the parent process.
    # Engines must still be cleared — inherited connections are fork-unsafe.
    # The companion `_session_registries.clear()` is gone with the registry
    # itself (2026-08-02); sessions are now per repository instance.
    # engine 仍須清除（fork 後連線不可共用）；session registry 已於 2026-08-02 移除。
    from src.data import database
    database._db_engines.clear()

    # Pre-warm the engine with NullPool
    database.get_db_engine()


# Explicit import to ensure Celery tasks are registered at worker startup
# The `imports` config in celery_config.py is set but Celery doesn't always
# auto-process it during the worker lifecycle. Direct import guarantees it.
import src.infrastructure.tasks  # noqa: F401

# Self-ops Loop 2 (2026-07-12): persist every task execution to task_runs —
# surfaces the "return 'Error: ...' into the void" legacy failure pattern.
from src.infrastructure.task_telemetry import register_task_telemetry
register_task_telemetry()

if __name__ == "__main__":
    app.start()
