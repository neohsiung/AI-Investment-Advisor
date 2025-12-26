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
        # Skip Saturday
        if get_current_time().weekday() == 5:
            msg = "Skipping Daily Check (Saturday) - Weekly Report runs today."
            logger.info(msg)
            self.log_job_execution("Daily Check", "SKIPPED", msg)
            return

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
        weekly_time = config.get("schedule_weekly", "09:00")
        
        # Convert User Time (e.g. Asia/Taipei) to System Time (UTC)
        daily_time_sys = convert_user_time_to_system_time(daily_time)
        weekly_time_sys = convert_user_time_to_system_time(weekly_time)
        
        logger.info(f"Loaded config: Daily={daily_time} ({daily_time_sys} UTC), Weekly={weekly_time} ({weekly_time_sys} UTC)")
        
        schedule.every().day.at(daily_time_sys).do(self.job_daily_check)
        schedule.every().saturday.at(weekly_time_sys).do(self.job_weekly_report)
        # Run validation on Sunday to review the week
        schedule.every().sunday.at("10:00").do(self.job_weekly_validation)
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
