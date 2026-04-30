import schedule
import time
import sys
import subprocess  # nosec B404
from src.utils.logger import setup_logger
logger = setup_logger("SchedulerService")

import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import uuid
import pytz
from datetime import datetime
from sqlalchemy import text
from src.agents.engineer import SystemEngineerAgent
from src.utils.time_utils import format_time, get_current_time, convert_user_time_to_system_time

# Helper function to get current UTC time
# 獲取目前 UTC 時間的輔助函式
def get_current_utc_time():
    """
    Get current UTC time.
    獲取目前 UTC 時間。
    """
    return datetime.now(pytz.utc)

class SchedulerService:
    """
    Service for managing scheduled jobs and background tasks.
    排程服務：管理排程任務與背景作業。
    """
    def __init__(self, user_id: str, db_engine: Any = None) -> None:
        """
        Initialize the scheduler service.
        初始化排程服務。
        """
        self.user_id = user_id
        self.engineer = None  # Lazy init — will be created on first job execution
        self.scheduler = schedule.Scheduler()
        # db_engine unused if we use get_db_connection, but keeping for DI signature
        # 如果我們使用 get_db_connection，db_engine 未被使用，但保留用於依賴注入簽名
    
    def log_job_execution(self, job_name: str, status: str, message: str = "") -> None:
        """
        Log job execution details to the database.
        將任務執行詳情記錄至資料庫。
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            
            engine = get_db_engine()
            with engine.begin() as conn:
                log_id = str(uuid.uuid4())
                # Save as UTC ISO with Z suffix to be unambiguous
                # 以帶有 Z 後綴的 UTC ISO 格式保存，以避免歧義
                timestamp = get_current_utc_time().isoformat().replace("+00:00", "Z")
                conn.execute(text("INSERT INTO scheduler_logs (id, timestamp, job_name, status, message) VALUES (:id, :timestamp, :job_name, :status, :message)"), {
                    "id": log_id,
                    "timestamp": timestamp,
                    "job_name": job_name,
                    "status": status,
                    "message": message
                })
        except Exception as e:
            logger.error(f"Error logging job: {e}")

    # get_all_users removed for strict single-user isolation (v5.0)

    def _ensure_engineer(self):
        """Lazy initialize Engineer agent on first use."""
        if self.engineer is None:
            try:
                self.engineer = SystemEngineerAgent(user_id=self.user_id)
                logger.info(f"Engineer agent initialized for user {self.user_id}")
            except Exception as e:
                logger.error(f"Failed to initialize Engineer: {e}")
                raise

    def job_daily_check(self):
        """Execute daily check for the current user context."""
        logger.info(f"Starting Daily Check Job for user {self.user_id}...")
        self._ensure_engineer()  # Initialize on first use
        if get_current_time().weekday() >= 5: # Sat=5, Sun=6
            logger.info("Skipping Daily Check on weekend.")
            return

        self.log_job_execution("Daily Check", "STARTED")
        
        try:
            # Using subprocess ensures clean memory state for heavy workflow
            subprocess.run([sys.executable, "services/scheduler/src/app.py", "--mode", "daily", "--user_id", self.user_id], check=True) # nosec
            self.log_job_execution("Daily Check", "COMPLETED")
        except Exception as e:
            logger.error(f"Daily Check failed for {self.user_id}: {e}")
            self.log_job_execution("Daily Check", "FAILED", str(e))

    def job_weekly_report(self):
        """Execute weekly report for the current user context."""
        logger.info(f"Starting Weekly Report Job for user {self.user_id}...")
        self.log_job_execution("Weekly Report", "STARTED")
        
        try:
            subprocess.run([sys.executable, "services/scheduler/src/app.py", "--mode", "weekly", "--user_id", self.user_id], check=True) # nosec
            self.log_job_execution("Weekly Report", "COMPLETED")
        except Exception as e:
            logger.error(f"Weekly Report failed for {self.user_id}: {e}")
            self.log_job_execution("Weekly Report", "FAILED", str(e))

    def job_weekly_validation(self):
        """
        Runs the Backtest Service to generate feedback examples from the past week.
        v5.0: Isolated to self.user_id.
        """
        logger.info(f"Starting Weekly Validation Job for user {self.user_id}...")
        self.log_job_execution("Weekly Validation", "STARTED")
        
        try:
            # Validation on major indices/stocks
            tickers = ["AAPL", "TSLA", "NVDA", "SPY"]
            
            from src.services.backtest_service import BacktestService
            service = BacktestService()
            
            for ticker in tickers:
                logger.info(f"Validating {ticker}...")
                service.run_simulation(ticker, days_back=7) # Review last week
                
            self.log_job_execution("Weekly Validation", "COMPLETED")
            
        except Exception as e:
            logger.error(f"Weekly Validation failed: {e}")
            self.log_job_execution("Weekly Validation", "FAILED", str(e))
            
            # Inline import to avoid circular dependency issues at module level
            from src.services.backtest_service import BacktestService
            service = BacktestService()
            
            for ticker in tickers:
                logger.info(f"Validating {ticker}...")
                service.run_simulation(ticker, days_back=7) # Review last week
                
            self.log_job_execution("Weekly Validation", "COMPLETED")
            
        except Exception as e:
            logger.error(f"Weekly Validation failed: {e}")
            self.log_job_execution("Weekly Validation", "FAILED", str(e))

    def job_experience_replay(self):
        """
        Runs the Experience Replay optimization to tune Sentinel thresholds based on history.
        v5.0: Isolated to self.user_id.
        """
        logger.info(f"Starting Experience Replay Optimization for user {self.user_id}...")
        self.log_job_execution("Experience Replay", "STARTED")
        
        try:
            from src.services.experience_replay_service import ExperienceReplayService
            service = ExperienceReplayService()
            
            results = service.optimize_thresholds(self.user_id)
            if results:
                self.log_job_execution("Experience Replay", "COMPLETED", f"Optimized: {results}")
            else:
                self.log_job_execution("Experience Replay", "COMPLETED", "No adjustments needed.")
                    
        except Exception as e:
            logger.error(f"Experience Replay failed: {e}")
            self.log_job_execution("Experience Replay", "FAILED", str(e))

    def job_monthly_refinement(self):
        logger.info("Starting Monthly Refinement...")
        try:
            subprocess.run([sys.executable, "src/refinement.py"], check=True) # nosec
            self.log_job_execution("Monthly Refinement", "COMPLETED")
        except Exception as e:
            self.log_job_execution("Monthly Refinement", "FAILED", str(e))

    def job_memory_distillation(self):
        """
        Rule #8: Cognitive Memory Distillation.
        Daily task to distill event logs into medium-term insights.
        """
        logger.info(f"Starting Memory Distillation for user {self.user_id}...")
        self.log_job_execution("Memory Distillation", "STARTED")
        try:
            from src.services.memory_distillation_service import MemoryDistillationService
            service = MemoryDistillationService(user_id=self.user_id)
            service.distill_daily_memory()
            self.log_job_execution("Memory Distillation", "COMPLETED")
        except Exception as e:
            logger.error(f"Memory Distillation failed for {self.user_id}: {e}")
            self.log_job_execution("Memory Distillation", "FAILED", str(e))

    def job_etoro_sync(self):
        """
        Sync Broker trade history for the current user.
        """
        logger.info(f"Starting Broker Sync Job for user {self.user_id}...")
        self.log_job_execution("Broker Sync", "STARTED")
        
        from src.services.broker_factory import BrokerFactory
        import asyncio
        
        try:
            # Get preferred broker for user
            broker = BrokerFactory.get_broker(self.user_id)
            broker_name = broker.get_name()
            
            # v7.1: sync_history is now properly async — run via asyncio.run()
            # Guard against reentrant loops (e.g. running inside an existing event loop)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop and loop.is_running():
                # Running inside an existing event loop (e.g., APScheduler async mode)
                # Schedule as a coroutine task
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    broker.sync_history(self.user_id), loop
                )
                result = future.result(timeout=120)
            else:
                result = asyncio.run(broker.sync_history(self.user_id))
            
            # Safely handle result
            if isinstance(result, dict):
                added = result.get('added', 0)
                skipped = result.get('skipped', 0)
                msg = f"Synced [{broker_name}]: +{added} / skipped {skipped}"
            else:
                msg = f"Synced [{broker_name}]: {result}"
            
            logger.info(msg)
            self.log_job_execution("Broker Sync", "COMPLETED", msg)
        except Exception as e:
            logger.error(f"Broker Sync failed for {self.user_id}: {e}")
            self.log_job_execution("Broker Sync", "FAILED", str(e))


    def check_monthly_job(self) -> None:
        """
        Check if today is the first of the month and trigger refinement if so.
        檢查今天是否為每月第一天，如果是則觸發進化任務。
        """
        if get_current_time().day == 1:
            self.job_monthly_refinement()

    def job_keyword_refine(self) -> None:
        """
        Weekly keyword lifecycle management: discover from 3 sources + refine weights.
        每週關鍵字生命週期管理：3 來源探索 + 自動調權。
        """
        logger.info("Starting Keyword Refine Job...")
        self.log_job_execution("Keyword Refine", "STARTED")
        try:
            from src.services.risk_keyword_service import RiskKeywordService
            import asyncio
            
            service = RiskKeywordService()
            
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(service.discover_and_refine())
            msg = (
                f"Discovered: reports={result['discovered']['reports']}, "
                f"webhook={result['discovered']['webhook']}, "
                f"trends={result['discovered']['trends']}. "
                f"Inserted {result['inserted']}, Pruned {result['pruned']}, "
                f"Refined: decay={result['refined']['decayed']}, boost={result['refined']['boosted']}. "
                f"Total: {result['total_after']}"
            )
            logger.info(f"Keyword Refine completed: {msg}")
            self.log_job_execution("Keyword Refine", "COMPLETED", msg)
        except Exception as e:
            logger.error(f"Keyword Refine failed: {e}")
            self.log_job_execution("Keyword Refine", "FAILED", str(e))

    def reload_schedule(self):
        """
        Reload the schedule from database configuration.
        從資料庫設定重新載入排程。
        """
        logger.info(f"Reloading schedule configuration for user {self.user_id}...")
        self._ensure_engineer()  # Initialize on first use
        self.scheduler.clear()
        
        config = self.engineer.get_schedule_config()
        daily_time = config.get("schedule_daily", "09:00")
        
        daily_days_str = config.get("schedule_daily_days", "monday,tuesday,wednesday,thursday,friday")
        daily_days = [d.strip().lower() for d in daily_days_str.split(",") if d.strip()]
        
        weekly_time = config.get("schedule_weekly", "09:00")
        weekly_day = config.get("schedule_weekly_day", "saturday").lower()
        
        # Convert User Time (e.g. Asia/Taipei) to System Time (Local)
        # 將使用者時間 (如 Asia/Taipei) 轉換為系統時間 (在地時間)
        daily_time_sys, daily_offset = convert_user_time_to_system_time(daily_time)
        weekly_time_sys, weekly_offset = convert_user_time_to_system_time(weekly_time)
        
        logger.info(f"[{self.user_id}] Loaded config: Daily={daily_time} ({daily_time_sys} System) on {daily_days}")
        
        # Helper to shift day
        days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        def get_shifted_day(day_name, offset):
            try:
                curr_idx = days_map.index(day_name.lower())
                new_idx = (curr_idx + offset) % 7
                return days_map[new_idx]
            except ValueError:
                return day_name

        # Schedule Daily Job
        for day in daily_days:
            target_day = get_shifted_day(day, daily_offset)
            if hasattr(self.scheduler.every(), target_day):
                getattr(self.scheduler.every(), target_day).at(daily_time_sys).do(self.job_daily_check)
                logger.debug(f"[{self.user_id}] Scheduled Daily Check on {target_day} at {daily_time_sys}")
        
        # Etoro Sync Job (Every 4 hours)
        self.scheduler.every(4).hours.do(self.job_etoro_sync)
        
        # Weekly Report
        target_weekly_day = get_shifted_day(weekly_day, weekly_offset)
        if hasattr(self.scheduler.every(), target_weekly_day):
            getattr(self.scheduler.every(), target_weekly_day).at(weekly_time_sys).do(self.job_weekly_report)
        else:
            self.scheduler.every().saturday.at(weekly_time_sys).do(self.job_weekly_report)
            
        # 哨兵心跳 (每分鐘)
        self.scheduler.every(1).minutes.do(self.job_minutely_tick)

    def job_minutely_tick(self) -> None:
        """
        Executes the Sentinel heart-beat tick to scan for market anomalies.
        執行哨兵心跳（每分鐘），掃描市場異常。
        """
        # Avoid log spam, use debug
        # logger.debug("Sentinel Tick...")
        try:
            # Inline import for dependency management
            from src.services.sentinel_service import SentinelService
            import asyncio
            
            # Run async sentinel logic in sync scheduler
            # v5.0: Strictly isolated to current user_id
            sentinel = SentinelService(user_id=self.user_id)
            
            # Check if there is an existing loop (unlikely in this thread, but safe check)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(sentinel.process_tick())
            
        except Exception as e:
            # Only log errors to keep logs clean
            logger.error(f"Sentinel Tick failed: {e}")

    def run_loop(self) -> None:
        """
        Start the infinite scheduler execution loop.
        開始無限排程執行迴圈。
        """
        self.reload_schedule()
        logger.info("Scheduler Service Running...")
        
        while True:
            schedule.run_pending()
            
            # Check signal
            if int(time.time()) % 5 == 0:
                self._check_reload_signal()
            
            time.sleep(1)

    def _check_reload_signal(self):
        """Check for reload signal every 5s with graceful error handling."""
        try:
            from src.repositories.settings_repository import AlchemySettingsRepository
            from src.data.database import get_db_engine
            
            # v5.1: Properly pass engine to repository
            settings_repo = AlchemySettingsRepository(engine=get_db_engine())
            
            # v4.3.4: Use self.user_id instead of 'SYSTEM' for reload signal
            val = settings_repo.get(self.user_id, 'scheduler_reload_signal')
            
            # Handle both boolean True and string "true" (str from DB, bool from ORM/v4)
            is_reload = str(val).lower() == "true" if not isinstance(val, bool) else val
            
            if is_reload:
                logger.info(f"Received reload signal for user {self.user_id}!")
                self.reload_schedule()
                # Reset signal using real boolean False
                settings_repo.set(self.user_id, 'scheduler_reload_signal', False)
            
            # Properly close the session after use
            settings_repo.close_session()
                
        except ValueError as ve:
            # Only log user isolation errors once to avoid spam
            if "Global 'system' user" not in str(ve):
                logger.warning(f"User isolation check failed: {ve}")
        except Exception as e:
            logger.debug(f"Error checking reload signal: {e}")

    def get_execution_logs(self, limit: int = 50):
        """Retrieves latest execution logs from DB."""
        # Ensure pandas is available
        import pandas as pd
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            
            engine = get_db_engine()
            with engine.connect() as conn:
                query = text("SELECT timestamp, job_name, status, message FROM scheduler_logs ORDER BY timestamp DESC LIMIT :limit")
                df = pd.read_sql(query, conn, params={"limit": limit})
                return df
        except Exception as e:
            logger.error(f"Error fetching scheduler logs: {e}")
            return pd.DataFrame()
