import argparse
import sys
import os

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.utils.logger import setup_logger
from src.utils.time_utils import format_time
from src.data.database import init_db

logger = setup_logger("Workflow")

def run_workflow(mode="daily", dry_run=False, user_id=None, force_report=False):
    """
    Orchestrates the investment advisory workflow using WorkflowService.
    
    Args:
        mode (str): 'daily' or 'weekly'
        dry_run (bool): If True, does not send email or save some states.
        user_id (str): The user to run for.
        force_report (bool): Force refresh/report generation.
    """
    print(f"[{format_time()}] Starting Workflow ({mode}) for User: {user_id or 'All'} [Force: {force_report}]...")
    
    # Ensure DB is initialized
    init_db()
    
    if not user_id:
        logger.error("user_id is required for workflow execution.")
        # We could implement iteration here, but scheduler handles it.
        return

    from src.services.workflow_service import DailyWorkflow, WeeklyWorkflow
    
    logger.info(f"Starting Workflow | Mode: {mode} | User: {user_id} | Dry Run: {dry_run}")
    print(f"[{format_time()}] Initializing {mode.capitalize()}Workflow...")

    try:
        if mode == 'daily':
            workflow = DailyWorkflow(user_id)
        elif mode == 'weekly':
            workflow = WeeklyWorkflow(user_id)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Execute using the Template Method
        result = workflow.run(dry_run=dry_run, force_refresh=force_report)
        
        logger.info("Workflow completed successfully.")
        return result

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        # Re-raise to ensure scheduler knows it failed
        raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=['daily', 'weekly'], default='weekly', help="Execution mode")
    parser.add_argument("--user_id", type=str, default=None, help="Specific User ID for SaaS mode")
    parser.add_argument("--force-report", action="store_true", help="Force generate report even if no significant changes")
    args = parser.parse_args()

    run_workflow(mode=args.mode, dry_run=args.dry_run, user_id=args.user_id, force_report=args.force_report)
