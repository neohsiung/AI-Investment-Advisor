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
USER_ID = "00000000-0000-4000-a000-000000000001"

app.conf.beat_schedule = {
    "pre-market-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=8, minute=30),  # 08:30 AM EST
        "args": (USER_ID,),
    },
    "mid-day-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=12, minute=0),   # 12:00 PM EST
        "args": (USER_ID,),
    },
    "post-market-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=16, minute=30),  # 04:30 PM EST
        "args": (USER_ID,),
    },
    "sentinel-minutely-tick": {
        "task": "src.infrastructure.tasks.sentinel_tick",
        "schedule": crontab(minute="*"),           # Every minute
        "args": (USER_ID,),
    },
    "broker-position-sync": {
        "task": "src.infrastructure.tasks.sync_broker_positions",
        "schedule": crontab(minute="*/5"),         # Every 5 minutes
        "args": (USER_ID,),
    },
    "daily-memory-distillation": {
        "task": "src.infrastructure.tasks.distill_memories",
        "schedule": crontab(hour=2, minute=0),     # 02:00 AM daily
        "args": (USER_ID,),
    },
    # P2-2: daily_report — 每個交易日 17:00 執行 (盤後報告)
    "daily-report": {
        "task": "src.infrastructure.tasks.generate_daily_report",
        "schedule": crontab(hour=17, minute=0, day_of_week="1-5"),  # Mon-Fri 17:00 EST (after market close)
        "args": (USER_ID,),
        "kwargs": {"force_report": False},
    },
    # P2-3: portfolio_rebalance — 每 30 分鐘於交易時段執行 (08:00-16:59 EST, Mon-Fri)
    "portfolio-rebalance-trigger": {
        "task": "src.infrastructure.tasks.trigger_portfolio_rebalance",
        "schedule": crontab(minute="*/30", hour="8-16", day_of_week="1-5"),
        "args": (USER_ID,),
    },
    "weekly-report-trigger": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=10, minute=0, day_of_week="6"),
        "args": (USER_ID,),
    },
    "weekly-cost-review": {
        "task": "src.infrastructure.tasks.distill_memories",
        "schedule": crontab(hour=22, minute=0, day_of_week="0"),
        "args": (USER_ID,),
    },
    "monthly-report": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=9, minute=0, day_of_month="1"),
        "args": (USER_ID,),
    },
    # P1-3: keyword_refine — 每週一 07:00 執行
    "weekly-keyword-refine": {
        "task": "src.infrastructure.tasks.keyword_refine",
        "schedule": crontab(hour=7, minute=0, day_of_week="1"),  # Mon 07:00
        "args": (USER_ID,),
    },
    # P1-4: experience_replay — 每週日 08:00 執行 (週日盤前復盤)
    "weekly-experience-replay": {
        "task": "src.infrastructure.tasks.experience_replay",
        "schedule": crontab(hour=8, minute=0, day_of_week="0"),  # Sun 08:00
        "args": (USER_ID,),
    },
    # P1-5: weekly_validation — 每週日 09:00 執行 (週日盤前回測驗證)
    "weekly-validation": {
        "task": "src.infrastructure.tasks.weekly_validation",
        "schedule": crontab(hour=9, minute=0, day_of_week="0"),  # Sun 09:00
        "args": (USER_ID,),
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

    # Force reload of engine if it was already initialized in the parent process
    from src.data import database
    database._db_engines.clear()
    database._session_registries.clear()

    # Pre-warm the engine with NullPool
    database.get_db_engine()


if __name__ == "__main__":
    app.start()
