import schedule
import time
import sys
import subprocess
from src.utils.logger import setup_logger
logger = setup_logger("SchedulerService")

from typing import Any, List, Dict, Optional
import uuid
import pytz
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
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
    def __init__(self, db_engine: Any = None) -> None:
        """
        Initialize the scheduler service.
        初始化排程服務。
        """
        self.engineer = SystemEngineerAgent()
        # db_engine unused if we use get_db_connection, but keeping for DI signature
        # 如果我們使用 get_db_connection，db_engine 未被使用，但保留用於依賴注入簽名
    
    def log_job_execution(self, job_name: str, status: str, message: str = "") -> None:
        """
        Log job execution details to the database.
        將任務執行詳情記錄至資料庫。
        """
        conn = get_db_connection()
        try:
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
            conn.commit()
        except Exception as e:
            logger.error(f"Error logging job: {e}")
        finally:
            conn.close()

    def get_all_users(self):
        conn = get_db_connection()
        try:
            rows = conn.execute(text("SELECT id, email FROM users")).fetchall()
            valid_users = []
            invalid_emails = ["admin@example.com", "your_email@gmail.com", "test@example.com"]
            for row in rows:
                uid, email = row[0], row[1]
                if email and email not in invalid_emails and not email.endswith("@example.com"):
                    valid_users.append(uid)
            return valid_users
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []
        finally:
            conn.close()

    def job_daily_check(self):
        # Strict adherence to Scheduler: If this function is called, it means it was scheduled.
        # We rely on reload_schedule to set the correct days.
        # 嚴格遵守排程器：如果此函式被呼叫，表示它已被排程。
        # 我們依賴 reload_schedule 來設定正確的日期。
        logger.info("Starting Daily Check Job...")
        self.log_job_execution("Daily Check", "STARTED")
        
        users = self.get_all_users()
        if not users:
            logger.warning("No users found.")
            return

        for user in users:
            try:
                # Use subprocess to isolate run context or use service?
                # Using subprocess ensures clean memory state for heavy workflow
                # But here we are refactoring, maybe we can run directly?
                # Subprocess is safer for long running daemon.
                # 使用 subprocess 來隔離執行上下文，還是直接使用 service？
                # 使用 subprocess 可確保大型工作流的記憶體狀態乾淨，這對長期運行的守護程序較安全。
                subprocess.run([sys.executable, "services/scheduler/src/app.py", "--mode", "daily", "--user_id", user], check=True) # nosec
                self.log_job_execution(f"Daily Check ({user})", "COMPLETED")
            except Exception as e:
                logger.error(f"Daily Check failed for {user}: {e}")
                self.log_job_execution(f"Daily Check ({user})", "FAILED", str(e))

    def job_weekly_report(self):
        logger.info("Starting Weekly Report Job...")
        self.log_job_execution("Weekly Report", "STARTED")
        
        users = self.get_all_users()
        for user in users:
            try:
                subprocess.run([sys.executable, "services/scheduler/src/app.py", "--mode", "weekly", "--user_id", user], check=True) # nosec
                self.log_job_execution(f"Weekly Report ({user})", "COMPLETED")
            except Exception as e:
                logger.error(f"Weekly Report failed for {user}: {e}")
                self.log_job_execution(f"Weekly Report ({user})", "FAILED", str(e))

    def job_weekly_validation(self):
        """
        Runs the Backtest Service to generate feedback examples from the past week.
        This closes the loop by providing fresh data for the Optimizer.
        """
        logger.info("Starting Weekly Validation Job...")
        self.log_job_execution("Weekly Validation", "STARTED")
        
        try:
            # We need to target active tickers.
            # Ideally, we query 'positions' or 'transactions' to get a set of relevant tickers.
            # For now, we will pick a predetermined set or query specific users.
            
            # TODO: Get distinct tickers from all users' portfolios
            # conn = get_db_connection()
            # tickers = conn.execute(text("SELECT DISTINCT ticker FROM positions")).fetchall()
            
            # Simplified: Validation on major indices/stocks
            tickers = ["AAPL", "TSLA", "NVDA", "SPY"]
            
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
        執行復盤優化任務，根據歷史數據調整哨兵閾值。
        """
        logger.info("Starting Experience Replay Optimization Job...")
        self.log_job_execution("Experience Replay", "STARTED")
        
        try:
            from src.services.experience_replay_service import ExperienceReplayService
            service = ExperienceReplayService()
            
            users = self.get_all_users()
            for user in users:
                logger.info(f"Optimizing for {user}...")
                results = service.optimize_thresholds(user)
                if results:
                    self.log_job_execution(f"Experience Replay ({user})", "COMPLETED", f"Optimized: {results}")
                else:
                    self.log_job_execution(f"Experience Replay ({user})", "COMPLETED", "No adjustments needed.")
                    
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

    def job_etoro_sync(self):
        """
        Sync Broker trade history (Etoro/Futu/etc.) for all users.
        """
        logger.info("Starting Broker Sync Job...")
        self.log_job_execution("Broker Sync", "STARTED")
        
        users = self.get_all_users()
        from src.services.broker_factory import BrokerFactory
        
        for user in users:
            try:
                # Get preferred broker for user
                broker = BrokerFactory.get_broker(user)
                broker_name = broker.get_name()
                
                result = broker.sync_history(user)
                msg = f"Synced {user} [{broker_name}]: +{result['added']} / skipped {result['skipped']}"
                logger.info(msg)
                self.log_job_execution(f"Broker Sync ({user})", "COMPLETED", msg)
            except Exception as e:
                logger.error(f"Broker Sync failed for {user}: {e}")
                self.log_job_execution(f"Broker Sync ({user})", "FAILED", str(e))

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
            service = RiskKeywordService()
            result = service.discover_and_refine()
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
        logger.info("Reloading schedule configuration...")
        schedule.clear()
        
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
        
        logger.info(f"Loaded config: Daily={daily_time} ({daily_time_sys} System, offset {daily_offset}) on {daily_days}, Weekly={weekly_day} {weekly_time} ({weekly_time_sys} System, offset {weekly_offset})")
        
        # Helper to shift day
        # 輔助函式：根據時區偏移調整執行日期
        days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        def get_shifted_day(day_name, offset):
            try:
                curr_idx = days_map.index(day_name.lower())
                new_idx = (curr_idx + offset) % 7
                return days_map[new_idx]
            except ValueError:
                return day_name # Fallback

        # Schedule Daily Job
        # 設定每日檢查排程
        for day in daily_days:
            target_day = get_shifted_day(day, daily_offset)
            if hasattr(schedule.every(), target_day):
                getattr(schedule.every(), target_day).at(daily_time_sys).do(self.job_daily_check)
                logger.info(f"Scheduled Daily Check on {target_day} at {daily_time_sys} System (User: {day} {daily_time})")
        
        # Etoro Sync Job (Every 4 hours)
        # 每 4 小時同步 Etoro 交易紀錄
        schedule.every(4).hours.do(self.job_etoro_sync)
        logger.info("Scheduled Etoro Sync every 4 hours.")
        
        # Dynamic day scheduling for Weekly Report
        # 設定每週報告的動態日期
        target_weekly_day = get_shifted_day(weekly_day, weekly_offset)
        if hasattr(schedule.every(), target_weekly_day):
            getattr(schedule.every(), target_weekly_day).at(weekly_time_sys).do(self.job_weekly_report)
            logger.info(f"Scheduled Weekly Report on {target_weekly_day} at {weekly_time_sys} System (User: {weekly_day} {weekly_time})")
        else:
            logger.warning(f"Invalid weekly day '{target_weekly_day}', defaulting to saturday.")
            schedule.every().saturday.at(weekly_time_sys).do(self.job_weekly_report)
            
        # Run validation on Sunday to review the week
        # 週日執行驗證、復盤與關鍵字精煉
        schedule.every().sunday.at("10:00").do(self.job_weekly_validation)
        schedule.every().sunday.at("11:00").do(self.job_experience_replay)
        schedule.every().sunday.at("12:00").do(self.job_keyword_refine)
        
        # Monthly Check (UTC 00:00)
        # 每月檢查 (UTC 00:00)
        schedule.every().day.at("00:00").do(self.check_monthly_job)

        # Sentinel Tick (Every Minute) - The Heartbeat of Agent Council
        # 哨兵心跳 (每分鐘)
        # In Local Mode, this drives the Sentinel. In Cloud, Cloud Scheduler drives it via API.
        schedule.every(1).minutes.do(self.job_minutely_tick)

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
            # Note: SentinelService needs to be robust and stateless
            sentinel = SentinelService()
            
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
        try:
            conn = get_db_connection()
            row = conn.execute(text("SELECT value FROM settings WHERE key='scheduler_reload_signal' AND user_id='SYSTEM'")).fetchone()
            if row and row[0] == 'true':
                logger.info("Received reload signal!")
                self.reload_schedule()
                conn.execute(text("UPDATE settings SET value='false' WHERE key='scheduler_reload_signal' AND user_id='SYSTEM'"))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error checking reload signal: {e}")

    def get_execution_logs(self, limit: int = 50):
        """Retrieves latest execution logs from DB."""
        # Ensure pandas is available
        import pandas as pd
        conn = get_db_connection()
        try:
            query = text("SELECT timestamp, job_name, status, message FROM scheduler_logs ORDER BY timestamp DESC LIMIT :limit")
            df = pd.read_sql(query, conn, params={"limit": limit})
            return df
        except Exception as e:
            logger.error(f"Error fetching scheduler logs: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
