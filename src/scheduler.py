import argparse
from src.services.scheduler_service import SchedulerService
from src.data.database import init_db

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investment Advisor Scheduler")
    parser.add_argument("--task", choices=['daily', 'weekly', 'monthly', 'loop'], default='loop',
                        help="Task to run immediately (or 'loop' for daemon mode)")
    args = parser.parse_args()

    # Initialize DB
    init_db()

    service = SchedulerService()
    
    if args.task == 'daily':
        service.job_daily_check()
    elif args.task == 'weekly':
        service.job_weekly_report()
    elif args.task == 'monthly':
        service.job_monthly_refinement()
    else:
        service.run_loop()
