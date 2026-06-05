import os
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime
from src.infrastructure.celery_app import app
from src.services.intelligence_service import IntelligenceService
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("CeleryTasks")

def is_market_open_today():
    """Checks if the NYSE is open today (EST)."""
    nyse = mcal.get_calendar("NYSE")
    today = pd.Timestamp.now(tz="US/Eastern").normalize()
    schedule = nyse.schedule(start_date=today, end_date=today)
    return not schedule.empty

import asyncio

def _run_async_safe(coro):
    """
    Safely runs an async coroutine from a synchronous Celery task.
    Handles nested event loop issues in some environments.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, we need to create a new one in a thread
            # or use a different approach. In Celery workers, it shouldn't be running.
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(coro)

@app.task(name="src.infrastructure.tasks.generate_market_intelligence")
def generate_market_intelligence(user_id: str = None):
    # ... check market open ...
    if not is_market_open_today():
        return "Skipped"

    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        settings_svc = SettingsService(user_id=user_id)
        intel_svc = IntelligenceService(settings_service=settings_svc, user_id=user_id)
        
        # 3. Execution (Async as sync)
        briefing = _run_async_safe(intel_svc.compute_briefing())
        
        # 4. Persistence
        settings_svc.save_setting("cached_intelligence_briefing", briefing, user_id=user_id)
        settings_svc.save_setting("last_intelligence_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        return "Success"
        
    except Exception as e:
        logger.error(f"Failed to generate intelligence in background: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.trigger_portfolio_rebalance")
def trigger_portfolio_rebalance(user_id: str = None):
    """
    Executes a high-priority rebalance check via SentinelService.
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.sentinel_service import SentinelService
        sentinel = SentinelService(user_id=user_id)
        _run_async_safe(sentinel.process_tick())
        return "Success"
    except Exception as e:
        logger.error(f"Failed to trigger rebalance in background: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.sentinel_tick")
def sentinel_tick(user_id: str = None):
    """
    Periodic heartbeat for Sentinel system (Minutely).
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.sentinel_service import SentinelService
        sentinel = SentinelService(user_id=user_id)
        _run_async_safe(sentinel.process_tick())
        return "Success"
    except Exception as e:
        logger.error(f"Sentinel heartbeat failed: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.sync_broker_positions")
def sync_broker_positions(user_id: str = None):
    """
    Syncs portfolio positions from broker (Every 5 mins).
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.transaction_service import TransactionService
        tx_svc = TransactionService(user_id=user_id)
        _run_async_safe(tx_svc.sync_broker_positions())
        return "Success"
    except Exception as e:
        logger.error(f"Broker sync failed: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.distill_memories")
def distill_memories(user_id: str = None):
    """
    Daily cognitive memory distillation.
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.cognitive_memory_manager import CognitiveMemoryManager
        memory_mgr = CognitiveMemoryManager(user_id=user_id)
        _run_async_safe(memory_mgr.distill_memories())
        return "Success"
    except Exception as e:
        logger.error(f"Memory distillation failed: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.experience_replay")
def experience_replay(user_id: str = None):
    """
    Weekly Experience Replay optimization to tune Sentinel thresholds based on history.
    每週經驗復盤：根據歷史警報頻率與績效動態調整 Sentinel 閾值。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.experience_replay_service import ExperienceReplayService
        svc = ExperienceReplayService()
        result = svc.optimize_thresholds(user_id)
        logger.info(f"experience_replay completed: {result}")
        return f"OK: {result}"
    except Exception as e:
        logger.error(f"experience_replay failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.keyword_refine")
def keyword_refine(user_id: str = None):
    """
    Weekly risk keyword discovery and weight refinement.
    每週風險關鍵字探索與權重精煉。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.risk_keyword_service import RiskKeywordService
        keyword_svc = RiskKeywordService()
        result = keyword_svc.refine()
        logger.info(f"keyword_refine completed: {result}")
        return f"OK: {result}"
    except Exception as e:
        logger.error(f"keyword_refine failed: {e}")
        return f"Error: {str(e)}"

    """
    Daily cognitive memory distillation.
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    try:
        from src.services.cognitive_memory_manager import CognitiveMemoryManager
        memory_mgr = CognitiveMemoryManager(user_id=user_id)
        _run_async_safe(memory_mgr.distill_memories())
        return "Success"
    except Exception as e:
        logger.error(f"Memory distillation failed: {e}")
        return f"Error: {str(e)}"
