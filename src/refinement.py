import logging
import sys
import os
sys.path.append(os.getcwd())
from datetime import datetime
from src.agents.engineer import SystemEngineerAgent
from src.services.performance_service import PerformanceService
from src.utils.logger import setup_logger

logger = setup_logger("MonthlyRefinement")

from src.services.refinement_service import RefinementService

import asyncio

def main():
    service = RefinementService()
    asyncio.run(service.run_monthly_refinement())

if __name__ == "__main__":
    main()

