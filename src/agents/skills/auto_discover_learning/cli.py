import sys
import argparse
import logging
import os
import json

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.services.investment_skill_learning_service import InvestmentSkillLearningService
from src.utils.logger import setup_logger

logger = setup_logger("auto_discover_learning_cli")

def main():
    parser = argparse.ArgumentParser(description="Trigger auto-discovery investment skill learning.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    
    args = parser.parse_args()
    
    try:
        svc = InvestmentSkillLearningService(user_id=args.user_id)
        result = svc.run_daily_learning()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"CLI auto_discover_learning failed: {e}")
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
