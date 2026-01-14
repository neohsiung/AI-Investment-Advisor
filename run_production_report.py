import sys
import os
import logging
from datetime import datetime

# Setup Path
sys.path.append(os.getcwd())

from src.services.workflow_service import WeeklyWorkflow
from src.services.task_planning_service import TaskPlanningService
from src.services.memory_factory import MemoryFactory
from src.notifier import EmailNotifier

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProductionReport")

def generate_and_send_report(user_id: str, dry_run: bool = False):
    logger.info(f"Starting Production Report Generation for {user_id}")
    
    # 1. Initialize Services
    # 初始化服務
    # Memory Service (Auto-selects Redis/SQLite based on Env)
    # 記憶服務 (根據環境自動選擇 Redis/SQLite)
    memory_service = MemoryFactory.create_memory_service(user_id)
    
    # Task Planner (Standard Plan)
    # 任務規劃器 (標準計畫)
    task_planner = TaskPlanningService()
    
    # Workflow
    # 工作流
    workflow = WeeklyWorkflow(user_id=user_id)
    workflow.memory_service = memory_service
    workflow.task_planner = task_planner
    
    # 2. Run Workflow (Antigravity Plan)
    # 執行工作流 (抗重力計畫)
    try:
        logger.info("Executing Weekly Workflow (Macro -> Micro)...")
        report_content = workflow.run_weekly_cycle(user_id)
        
        print("\n" + "="*50)
        print("Generated Weekly Report Preview:")
        print("="*50)
        print(report_content[:1000] + "...\n[Truncated for Console]")
        print("="*50 + "\n")
        
        # 3. Distribution
        # 分發報告
        if not dry_run:
            logger.info("Distributing Report via Email...")
            notifier = EmailNotifier()
            subject = f"Weekly AI Investment Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Attempt to send (might fail if no creds, but we try)
            try:
                notifier.send_report(subject, report_content) 
                logger.info("Email sent successfully.")
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                logger.info("Proceeding to save to disk as backup.")
                with open("weekly_report_lnatest.md", "w") as f:
                    f.write(report_content)
        else:
            logger.info("Dry Run: Email skipped.")
            
    except Exception as e:
        logger.error(f"Report Generation Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Default User
    USER_ID = "supermfb@gmail.com"
    generate_and_send_report(USER_ID, dry_run=False)
