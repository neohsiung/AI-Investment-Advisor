import argparse
import sys
import os
from dotenv import load_dotenv

if sys.version_info < (3, 10):
    sys.exit("Error: This project requires Python 3.10 or higher. Your current version is " + sys.version)

# Load environment variables from .env file
load_dotenv()

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.utils.logger import setup_logger
from src.utils.time_utils import format_time
from src.data.database import init_db

import asyncio

logger = setup_logger("Workflow")

async def run_workflow(mode="daily", dry_run=False, user_id=None, force_report=False):
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
        result = await workflow.run(dry_run=dry_run, force_refresh=force_report)
        
        logger.info("Workflow completed successfully.")
        return result

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        # Re-raise to ensure scheduler knows it failed
        raise e

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=['daily', 'weekly', 'backtest', 'optimize', 'scheduler'], default='weekly', help="Execution mode")
    parser.add_argument("--task", choices=['daily', 'weekly', 'monthly'], help="Specific task for scheduler mode (optional, defaults to loop)")
    parser.add_argument("--user_id", type=str, default=None, help="Specific User ID for SaaS mode")
    parser.add_argument("--ticker", type=str, default="AAPL", help="Ticker for backtest")
    parser.add_argument("--force-report", action="store_true", help="Force generate report even if no significant changes")
    args = parser.parse_args()

    if args.mode == 'backtest':
        from src.services.backtest_service import BacktestService
        BacktestService().run_simulation(args.ticker, days_back=30)
    elif args.mode == 'optimize':
        from src.workflow.optimizer import OptimizerPipeline
        pipeline = OptimizerPipeline()
        # Train on Momentum Agent examples
        trainset = pipeline.load_training_data(agent_name="Momentum")
        if trainset:
            pipeline.optimize_momentum_agent(trainset)
            
    elif args.mode == 'scheduler':
        from src.services.scheduler_service import SchedulerService
        print(f"[{format_time()}] Starting Scheduler Service...")
        service = SchedulerService()
        
        if args.task:
            # Single task execution
            if args.task == 'daily':
                service.job_daily_check()
            elif args.task == 'weekly':
                service.job_weekly_report()
            elif args.task == 'monthly':
                service.job_monthly_refinement()
        else:
            # Daemon loop
            service.run_loop()
            
    else:
        asyncio.run(run_workflow(mode=args.mode, dry_run=args.dry_run, user_id=args.user_id, force_report=args.force_report))

if __name__ == "__main__":
    main()
