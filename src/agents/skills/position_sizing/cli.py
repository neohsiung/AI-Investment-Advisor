import sys
import argparse
import logging
import os
import json

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.services.broker_factory import BrokerFactory
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.logger import setup_logger

logger = setup_logger("position_sizing_cli")

def _is_ticker_match(t1: str, t2: str) -> bool:
    """Check if two ticker symbols match, ignoring eToro suffixes."""
    if not t1 or not t2:
        return False
    def normalize(s):
        s = s.strip().upper()
        for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
            if s.endswith(suffix):
                return s[: -len(suffix)]
        return s
    return normalize(t1) == normalize(t2)

def main():
    parser = argparse.ArgumentParser(description="Calculate appropriate trade quantity.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--action", required=True, choices=["BUY", "SELL"], help="Trade action")
    parser.add_argument("--desired_quantity", type=float, default=0.0, help="Desired quantity")
    parser.add_argument("--intent", default="auto", choices=["auto", "full_close", "partial_reduce"], help="Trade intent")
    
    args = parser.parse_args()
    
    try:
        broker = BrokerFactory.get_broker(args.user_id)
        if not broker:
            print(json.dumps({"recommended_quantity": 0, "reason": "No broker configured"}))
            return

        account = broker.get_account()
        positions = broker.get_positions()

        nlv = account.total_equity if account else 0
        cash = account.available_cash if account else 0
        cash_ratio_before = (cash / nlv) if nlv > 0 else 0

        # Find actual holding for this ticker
        actual_holding = 0.0
        for p in positions:
            if _is_ticker_match(args.ticker, p.symbol):
                actual_holding += p.quantity

        settings = AlchemySettingsRepository()
        max_pct = float(settings.get(args.user_id, "max_single_position_pct") or 0.10)
        min_amount = float(settings.get(args.user_id, "min_trade_amount") or 10.0)

        action_upper = args.action.upper()
        reason = ""

        if action_upper == "SELL":
            if actual_holding <= 0:
                print(json.dumps({
                    "recommended_quantity": 0,
                    "actual_holding": 0,
                    "cash_ratio_before": round(cash_ratio_before, 4),
                    "reason": f"No active position found for {args.ticker}. Cannot sell.",
                }))
                return

            if args.intent == "full_close":
                recommended = actual_holding
                reason = f"Full close of {args.ticker} position ({actual_holding} units)"
            elif args.intent == "partial_reduce":
                recommended = min(args.desired_quantity, actual_holding) if args.desired_quantity > 0 else actual_holding * 0.5
                reason = f"Partial reduce: {recommended} of {actual_holding} units"
            else:  # auto
                if args.desired_quantity > 0:
                    recommended = min(args.desired_quantity, actual_holding)
                    if args.desired_quantity > actual_holding:
                        reason = f"Clamped SELL from {args.desired_quantity} to {actual_holding} (actual holding)"
                    else:
                        reason = f"SELL {recommended} of {actual_holding} units"
                else:
                    recommended = actual_holding
                    reason = f"No quantity specified, defaulting to full close ({actual_holding} units)"

        elif action_upper == "BUY":
            max_amount = nlv * max_pct if nlv > 0 else 0
            recommended = args.desired_quantity if args.desired_quantity > 0 else min_amount

            if recommended > cash:
                reason += f"Clamped from ${recommended:.2f} to ${cash:.2f} (available cash). "
                recommended = cash
            if recommended > max_amount and max_amount > 0:
                reason += f"Clamped to ${max_amount:.2f} ({max_pct*100:.0f}% of NLV ${nlv:.2f}). "
                recommended = max_amount
            if recommended < min_amount:
                reason += f"Below minimum ${min_amount:.2f}. "
                recommended = 0
            if not reason:
                reason = f"Within limits (max position {max_pct*100:.0f}% of NLV)"
        else:
            print(json.dumps({"recommended_quantity": 0, "reason": f"Unknown action: {args.action}"}))
            return

        # Estimate post-trade cash ratio
        cash_after = cash
        if action_upper == "BUY":
            cash_after = cash - recommended
        cash_ratio_after = (cash_after / nlv) if nlv > 0 else 0

        print(json.dumps({
            "recommended_quantity": round(recommended, 4),
            "actual_holding": round(actual_holding, 4),
            "cash_ratio_before": round(cash_ratio_before, 4),
            "cash_ratio_after_estimate": round(cash_ratio_after, 4),
            "reason": reason.strip(),
        }, ensure_ascii=False))

    except Exception as e:
        logger.error(f"CLI position_sizing failed: {e}")
        print(json.dumps({"recommended_quantity": 0, "reason": f"Error: {e}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
