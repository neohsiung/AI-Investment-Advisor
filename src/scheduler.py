import schedule
import time
import subprocess
import argparse
import sys
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

def run_scheduler_loop():
    print(f"Scheduler started at {format_time()}. Press Ctrl+C to exit.")
    
    from src.agents.engineer import SystemEngineerAgent
    engineer = SystemEngineerAgent()
    
    # 初始讀取配置
    config = engineer.get_schedule_config()
    daily_time = config.get("schedule_daily", "09:00")
    weekly_time = config.get("schedule_weekly", "09:00")
    
    print(f"Loaded schedule config: Daily at {daily_time}, Weekly at {weekly_time}")
    
    # 每日執行檢查 (Daily Mode)
    schedule.every().day.at(daily_time).do(job_daily_check)
    
    # 每週六執行週報 (Weekly Mode)
    schedule.every().saturday.at(weekly_time).do(job_weekly_report)
    
    # 每月 1 號執行 Refinement
    schedule.every().day.at("00:00").do(check_monthly_job)
    
    # 定期重新加載配置 (例如每小時)
    # 為了簡單起見，目前若要更改配置需重啟 Scheduler，
    # 或者我們可以在 loop 中檢查 DB 變更 (較複雜)。
    # 這裡先保持靜態載入，但至少是從 DB 讀的。
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investment Advisor Scheduler")
    parser.add_argument("--task", choices=['daily', 'weekly', 'monthly', 'loop'], default='loop', 
                        help="Task to run immediately (or 'loop' for daemon mode)")
    args = parser.parse_args()

    if args.task == 'daily':
        job_daily_check()
    elif args.task == 'weekly':
        job_weekly_report()
    elif args.task == 'monthly':
        job_monthly_refinement()
    else:
        run_scheduler_loop()
