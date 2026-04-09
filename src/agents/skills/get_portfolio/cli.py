import sys
import argparse
import logging
import os

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.utils.logger import setup_logger

logger = setup_logger("get_portfolio_cli")

def main():
    parser = argparse.ArgumentParser(description="Fetch portfolio summary for a user.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    
    args = parser.parse_args()
    
    try:
        repo = AlchemyTransactionRepository()
        summary = repo.get_holdings_summary(args.user_id)
        leverage = repo.get_latest_leverage(args.user_id)
        print(f"Leverage: {leverage:.2f}")
        print(f"Holdings: {summary}")
    except Exception as e:
        logger.error(f"CLI get_portfolio failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
