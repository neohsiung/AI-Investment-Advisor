import sys
import argparse
import logging
import os
import json

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.services.etoro_service import EtoroService
from src.utils.logger import setup_logger

logger = setup_logger("etoro_trade_cli")

def main():
    parser = argparse.ArgumentParser(description="Execute trades on Etoro.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "STATUS"], help="Trade action or status check")
    parser.add_argument("--ticker", help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--amount", type=float, help="Amount in USD")
    parser.add_argument("--leverage", type=int, default=1, help="Leverage (1, 2, 5...)")
    parser.add_argument("--reason", default="AI Decision", help="Reason for the trade")
    
    args = parser.parse_args()
    
    try:
        service = EtoroService()
        
        if args.action == "STATUS":
            enabled = service.check_constraints(args.user_id)
            print(json.dumps({
                "trading_enabled": enabled,
                "system_status": "NORMAL" if enabled else "PAUSED_RISK_CONTROL"
            }, indent=2))
            return

        if not args.ticker or not args.amount:
            print("Error: --ticker and --amount are required for BUY/SELL actions.")
            sys.exit(1)

        result = service.execute_trade(
            user_id=args.user_id,
            ticker=args.ticker,
            action=args.action.upper(),
            amount=args.amount,
            leverage=args.leverage,
            reason=args.reason
        )
        print(json.dumps(result, indent=2))
            
    except Exception as e:
        logger.error(f"CLI etoro_trade failed: {e}")
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
