import logging
import sys
import os
sys.path.append(os.getcwd())
from datetime import datetime
from src.agents.engineer import SystemEngineerAgent
from src.services.performance_service import PerformanceService
from src.notifier import EmailNotifier
from src.utils.logger import setup_logger

logger = setup_logger("MonthlyRefinement")

from src.services.refinement_service import RefinementService

def main():
    service = RefinementService()
    service.run_monthly_refinement()

if __name__ == "__main__":
    main()

