import schedule
import time
import sys
import subprocess
import logging
import uuid
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
from src.agents.engineer import SystemEngineerAgent
from src.utils.time_utils import format_time, get_current_time, convert_user_time_to_system_time

logger = logging.getLogger("SchedulerService")

class SchedulerService:
    def __init__(self, db_engine=None):
        self.engineer = SystemEngineerAgent()
        # db_engine unused if we use get_db_connection, but keeping for DI signature
    
    def log_job_execution(self, job_name, status, message=""):
        conn = get_db_connection()
        try:
            log_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
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
            rows = conn.execute(text("SELECT email FROM users")).fetchall()
            users = [row[0] for row in rows]
            invalid_emails = ["admin@example.com", "your_email@gmail.com"]
            return [u for u in users if u and u not in invalid_emails and not u.endswith("@example.com")]
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []
        finally:
            conn.close()

    def job_daily_check(self):
        # Strict adherence to Scheduler: If this function is called, it means it was scheduled.
        # We rely on reload_schedule to set the correct days.
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
                subprocess.run([sys.executable, "src/cli.py", "--mode", "daily", "--user_id", user], check=True)
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
                subprocess.run([sys.executable, "src/cli.py", "--mode", "weekly", "--user_id", user], check=True)
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

    def job_monthly_refinement(self):
        logger.info("Starting Monthly Refinement...")
        try:
            subprocess.run([sys.executable, "src/refinement.py"], check=True)
            self.log_job_execution("Monthly Refinement", "COMPLETED")
        except Exception as e:
            self.log_job_execution("Monthly Refinement", "FAILED", str(e))

    def check_monthly_job(self):
        if get_current_time().day == 1:
            self.job_monthly_refinement()

    def reload_schedule(self):
        logger.info("Reloading schedule configuration...")
        schedule.clear()
        
        config = self.engineer.get_schedule_config()
        daily_time = config.get("schedule_daily", "09:00")
        
        daily_days_str = config.get("schedule_daily_days", "monday,tuesday,wednesday,thursday,friday")
        daily_days = [d.strip().lower() for d in daily_days_str.split(",") if d.strip()]
        
        weekly_time = config.get("schedule_weekly", "09:00")
        weekly_day = config.get("schedule_weekly_day", "saturday").lower()
        
        # Convert User Time (e.g. Asia/Taipei) to System Time (UTC)
        # 將使用者時間 (如 Asia/Taipei) 轉換為系統時間 (UTC)
        daily_time_sys, daily_offset = convert_user_time_to_system_time(daily_time)
        weekly_time_sys, weekly_offset = convert_user_time_to_system_time(weekly_time)
        
        logger.info(f"Loaded config: Daily={daily_time} ({daily_time_sys} UTC, offset {daily_offset}) on {daily_days}, Weekly={weekly_day} {weekly_time} ({weekly_time_sys} UTC, offset {weekly_offset})")
        
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
                logger.info(f"Scheduled Daily Check on {target_day} at {daily_time_sys} UTC (User: {day} {daily_time})")
        
        # Dynamic day scheduling for Weekly Report
        # 設定每週報告的動態日期
        target_weekly_day = get_shifted_day(weekly_day, weekly_offset)
        if hasattr(schedule.every(), target_weekly_day):
            getattr(schedule.every(), target_weekly_day).at(weekly_time_sys).do(self.job_weekly_report)
            logger.info(f"Scheduled Weekly Report on {target_weekly_day} at {weekly_time_sys} UTC (User: {weekly_day} {weekly_time})")
        else:
            logger.warning(f"Invalid weekly day '{target_weekly_day}', defaulting to saturday.")
            schedule.every().saturday.at(weekly_time_sys).do(self.job_weekly_report)
            
        # Run validation on Sunday to review the week
        # 週日執行驗證以回顧本週表現
        # Validation time also needs checking, assuming fixed 10:00 UTC for now or user time?
        # Let's align with Weekly report logic roughly (+2 hours)
        # Using fixed Sunday 10:00 UTC for simplicity as before
        schedule.every().sunday.at("10:00").do(self.job_weekly_validation)
        
        # Monthly Check (UTC 00:00)
        # 每月檢查 (UTC 00:00)
        schedule.every().day.at("00:00").do(self.check_monthly_job)

    def run_loop(self):
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
