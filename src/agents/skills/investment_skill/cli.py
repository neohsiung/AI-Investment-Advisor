import sys
import argparse
import logging
import os

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.services.investment_skill_learning_service import InvestmentSkillLearningService
from src.utils.logger import setup_logger

logger = setup_logger("investment_skill_cli")

def main():
    parser = argparse.ArgumentParser(description="Query applicable investment skills.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--timeframe", default="", help="Filtered timeframe")
    parser.add_argument("--market_regime", default="", help="Filtered market regime")
    parser.add_argument("--industry", default="", help="Filtered industry")
    parser.add_argument("--technique", default="", help="Filtered technique")
    
    args = parser.parse_args()
    
    try:
        svc = InvestmentSkillLearningService(user_id=args.user_id)
        skills = svc.get_applicable_skills(
            timeframe=args.timeframe,
            market_regime=args.market_regime,
            industry=args.industry,
            technique=args.technique,
        )

        if not skills:
            print("No applicable investment skills found for the given context.")
            return

        print(f"Found {len(skills)} applicable investment skills:\n")
        for s in skills:
            print(f"### {s.get('name', 'Unnamed')}")
            print(f"- **Technique**: {s.get('technique', 'N/A')}")
            print(f"- **Timeframe**: {s.get('timeframe', 'N/A')}")
            print(f"- **Description**: {s.get('description', 'N/A')}")
            print(f"- **Usage Count**: {s.get('usage_count', 0)}\n")
            
    except Exception as e:
        logger.error(f"CLI investment_skill failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
