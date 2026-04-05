import os
from celery import Celery
from celery.schedules import crontab

# v2.1: Initialize Celery with Redis as the broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("investment_advisor", broker=redis_url, backend=redis_url)

# v2.3: Configure Timezone to US/Eastern for Market-aware scheduling
app.conf.timezone = "US/Eastern"
app.conf.task_track_started = True

# Define Periodic Tasks (Celery Beat)
app.conf.beat_schedule = {
    "pre-market-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=8, minute=30),  # 08:30 AM EST
    },
    "mid-day-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=12, minute=0),   # 12:00 PM EST
    },
    "post-market-intelligence": {
        "task": "src.infrastructure.tasks.generate_market_intelligence",
        "schedule": crontab(hour=17, minute=0),  # 05:00 PM EST
    },
}

# Auto-discover tasks in the infrastructure directory
app.autodiscover_tasks(["src.infrastructure"])

# v7.3: Process Isolation & Database Pool Hardening
from celery.signals import worker_process_init
from src.utils.logger import setup_logger

logger = setup_logger("CeleryHooks")

@worker_process_init.connect
def setup_db_worker_context(**kwargs):
    """
    Ensure each worker process has a clean database engine and is flagged 
    to use NullPool to avoid connection sharing across forks.
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
