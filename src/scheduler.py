import schedule
import time
import os
import threading
import subprocess # nosec B404
import uuid
import sys
import argparse
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection, init_db
from src.utils.time_utils import get_current_time, format_time # Keep these as they are used elsewhere

def log_scheduler_event(job_name, status, message=""):
    """Wrapper for log_job_execution to maintain compatibility"""
    log_job_execution(job_name, status, message)

def log_job_execution(job_name, status, message=""):
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
        print(f"Error logging job: {e}")
    finally:
        conn.close()

def get_all_users():
    """Fetch all user IDs (emails) from the database."""
    conn = get_db_connection()
    try:
        # Assuming we have a users table now or we derive from unique user_ids in transactions?
        # Ideally we use the users table.
        users = []
        try:
             rows = conn.execute(text("SELECT email FROM users")).fetchall()
             users = [row[0] for row in rows]
        except Exception:
             # Fallback if users table empty or missing (legacy mode?)
             pass # nosec B110
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []
    finally:
        conn.close()

def job_weekly_report():
    print(f"[{format_time()}] Starting Weekly Report Job...")
    log_job_execution("Weekly Report", "STARTED", "Job started.")

    users = get_all_users()
    if not users:
        print("No users found. Skipping.")
        return

    for user in users:
        print(f"[{format_time()}] Running Weekly Report for {user}...")
        try:
            # 執行 workflow.py (Weekly Mode) with user_id
            subprocess.run([sys.executable, "src/workflow.py", "--mode", "weekly", "--user_id", user], check=True) # nosec B603
            log_scheduler_event(f"Weekly Report ({user})", "COMPLETED", "Job completed successfully.")
        except Exception as e:
            print(f"[{format_time()}] Weekly Report Job Failed for {user}: {e}")
            log_scheduler_event(f"Weekly Report ({user})", "FAILED", str(e))

    print(f"[{format_time()}] Weekly Report Job Batch Completed.")

def job_daily_check():
    # 週六不執行每日檢查，因為有週報
    if get_current_time().weekday() == 5:
        print(f"[{format_time()}] Skipping Daily Check (Saturday).")
        return

    print(f"[{format_time()}] Starting Daily Check Job...")
    log_job_execution("Daily Check", "STARTED", "Job started.")

    users = get_all_users()
    if not users:
        print("No users found. Skipping.")
        return

    for user in users:
        print(f"[{format_time()}] Running Daily Check for {user}...")
        try:
            # 執行 workflow.py (Daily Mode) with user_id
            subprocess.run([sys.executable, "src/workflow.py", "--mode", "daily", "--user_id", user], check=True) # nosec B603
            log_job_execution(f"Daily Check ({user})", "COMPLETED", "Job completed successfully.")
        except Exception as e:
            print(f"[{format_time()}] Daily Check Job Failed for {user}: {e}")
            log_job_execution(f"Daily Check ({user})", "FAILED", str(e))

    print(f"[{format_time()}] Daily Check Job Batch Completed.")

def job_monthly_refinement():
    print(f"[{format_time()}] Starting Monthly Refinement Job...")
    log_job_execution("Monthly Refinement", "STARTED", "Job started.")
    # Refinement might differ? For now run global or per user?
    # Refinement agent (Engineer) optimizes prompts.
    # Prompts are in `src/prompts.py` which are code files.
    # So optimization is global for the codebase.
    # However, if we store prompts in DB per user later, this needs change.
    # For now, let's keep it global or maybe just run once?
    # If it writes to code, it's global.
    try:
        # 執行 refinement.py
        subprocess.run([sys.executable, "src/refinement.py"], check=True) # nosec B603
        print(f"[{format_time()}] Monthly Refinement Job Completed.")
        log_job_execution("Monthly Refinement", "COMPLETED", "Job completed successfully.")
    except Exception as e:
        print(f"[{format_time()}] Monthly Refinement Job Failed: {e}")
        log_job_execution("Monthly Refinement", "FAILED", str(e))

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

    # Initialize DB (Safe to call repeatedly, checks IF NOT EXISTS)
    # This ensures tables exist even if scheduler container starts first or alone
    init_db()

    if args.task == 'daily':
        job_daily_check()
    elif args.task == 'weekly':
        job_weekly_report()
    elif args.task == 'monthly':
        job_monthly_refinement()
    else:
        run_scheduler_loop()
