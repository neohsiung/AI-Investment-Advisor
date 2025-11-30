import schedule
import time
import subprocess
from src.database import get_db_connection
import uuid
from src.utils.time_utils import get_current_time, format_time

def log_scheduler_event(job_name, status, message=""):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        log_id = str(uuid.uuid4())
        timestamp = format_time() # Use standardized time
        cursor.execute("INSERT INTO scheduler_logs (id, timestamp, job_name, status, message) VALUES (?, ?, ?, ?, ?)",
                       (log_id, timestamp, job_name, status, message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging scheduler event: {e}")

def job_weekly_report():
    print(f"[{format_time()}] Starting Weekly Report Job...")
    log_scheduler_event("Weekly Report", "STARTED", "Job started.")
    try:
        # 執行 workflow.py (Weekly Mode)
        subprocess.run(["python3", "src/workflow.py", "--mode", "weekly"], check=True)
        print(f"[{format_time()}] Weekly Report Job Completed.")
        log_scheduler_event("Weekly Report", "COMPLETED", "Job completed successfully.")
    except Exception as e:
        print(f"[{format_time()}] Weekly Report Job Failed: {e}")
        log_scheduler_event("Weekly Report", "FAILED", str(e))

def job_daily_check():
    # 週六不執行每日檢查，因為有週報
    # Note: get_current_time() returns timezone-aware datetime
    if get_current_time().weekday() == 5:
        print(f"[{format_time()}] Skipping Daily Check (Saturday).")
        return

    print(f"[{format_time()}] Starting Daily Check Job...")
    log_scheduler_event("Daily Check", "STARTED", "Job started.")
    try:
        # 執行 workflow.py (Daily Mode)
        subprocess.run(["python3", "src/workflow.py", "--mode", "daily"], check=True)
        print(f"[{format_time()}] Daily Check Job Completed.")
        log_scheduler_event("Daily Check", "COMPLETED", "Job completed successfully.")
    except Exception as e:
        print(f"[{format_time()}] Daily Check Job Failed: {e}")
        log_scheduler_event("Daily Check", "FAILED", str(e))

def job_monthly_refinement():
    print(f"[{format_time()}] Starting Monthly Refinement Job...")
    log_scheduler_event("Monthly Refinement", "STARTED", "Job started.")
    try:
        # 執行 refinement.py
        subprocess.run(["python3", "src/refinement.py"], check=True)
        print(f"[{format_time()}] Monthly Refinement Job Completed.")
        log_scheduler_event("Monthly Refinement", "COMPLETED", "Job completed successfully.")
    except Exception as e:
        print(f"[{format_time()}] Monthly Refinement Job Failed: {e}")
        log_scheduler_event("Monthly Refinement", "FAILED", str(e))

def check_monthly_job():
    if get_current_time().day == 1:
        job_monthly_refinement()

def run_scheduler():
    print(f"Scheduler started at {format_time()}. Press Ctrl+C to exit.")
    
    # 每日 09:00 執行檢查 (Daily Mode)
    # Note: schedule uses system time. If system is UTC, this is 09:00 UTC.
    # To strictly follow Taipei time for scheduling, we might need to adjust or set system TZ.
    # For now, we assume the container/system TZ is aligned or user accepts system time trigger.
    schedule.every().day.at("09:00").do(job_daily_check)
    
    # 每週六 09:00 執行週報 (Weekly Mode)
    schedule.every().saturday.at("09:00").do(job_weekly_report)
    
    # 每月 1 號執行 Refinement
    schedule.every().day.at("00:00").do(check_monthly_job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
