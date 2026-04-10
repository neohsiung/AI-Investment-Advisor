import sys
import argparse
import logging
import os
import json
import asyncio

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.services.broker_factory import BrokerFactory
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.logger import setup_logger
from src.agents.skills.ticker_discovery.impl import ticker_discovery

logger = setup_logger("cash_deployment_cli")

async def cash_deployment(user_id: str) -> str:
    """
    分析閒置現金並提供部署建議。
    Analyze idle cash and provide deployment suggestions.
    """
    try:
        # 1. Initialize resources
        settings_repo = AlchemySettingsRepository()
        broker = BrokerFactory.get_broker(user_id)
        
        if not broker:
            logger.error(f"No broker found for user {user_id}")
            return json.dumps({
                "error": f"No broker found for user {user_id}",
                "status": "error"
            })

        # 2. Retrieve account data
        account = broker.get_account()
        if not account or account.total_equity <= 0:
            logger.error(f"Failed to retrieve account data for user {user_id}")
            return json.dumps({
                "error": "Failed to retrieve account data or equity is zero",
                "status": "error"
            })

        # Get target_cash_ratio from settings (default 10%)
        target_val = settings_repo.get(user_id, "target_cash_ratio", 0.10)
        try:
            target_cash_ratio = float(target_val)
        except (ValueError, TypeError):
            target_cash_ratio = 0.10

        available_cash = account.available_cash
        total_equity = account.total_equity
        
        actual_ratio = available_cash / total_equity
        target_cash_amount = total_equity * target_cash_ratio
        excess_cash = available_cash - target_cash_amount

        # 3. Determine status
        if excess_cash <= 1.0: # Ignore dust
            return json.dumps({
                "status": "balanced",
                "cash_ratio": round(actual_ratio, 4),
                "target_ratio": round(target_cash_ratio, 4),
                "excess_cash": 0.0,
                "currency": account.currency,
                "message": f"Cash ratio is healthy ({actual_ratio*100:.1f}%)"
            }, ensure_ascii=False)

        # 4. Get deployment candidates
        candidates = await _get_deployment_candidates(user_id, excess_cash)

        return json.dumps({
            "status": "overweight",
            "cash_ratio": round(actual_ratio, 4),
            "target_ratio": round(target_cash_ratio, 4),
            "excess_cash": round(excess_cash, 2),
            "currency": account.currency,
            "candidates": candidates,
            "message": f"Excess cash detected: ${excess_cash:,.2f}. Ready for deployment."
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"cash_deployment skill failed for user {user_id}: {e}", exc_info=True)
        return json.dumps({"error": str(e), "status": "error"})

async def _get_deployment_candidates(user_id: str, amount: float) -> list:
    """獲取建議部署的標的清單。"""
    core_candidates = [
        {"ticker": "VOO", "reason": "Strategic Market Core (S&P 500)", "weight": 0.5},
        {"ticker": "QQQ", "reason": "Technology Growth Focus (Nasdaq 100)", "weight": 0.5}
    ]
    
    results = []
    core_amount = amount * 0.8
    for c in core_candidates:
        allocated = core_amount * c["weight"]
        results.append({
            "ticker": c["ticker"],
            "allocated_amount": round(allocated, 2),
            "reason": c["reason"],
            "source": "strategic_core"
        })
            
    # Alpha Discovery (20%)
    try:
        discovery_res_json = await ticker_discovery(user_id, strategy="growth")
        discovery_data = json.loads(discovery_res_json)
        
        if discovery_data.get("status") == "success":
            discovered = discovery_data.get("tickers", [])
            if discovered:
                alpha_amount = amount * 0.2
                alpha_candidates = discovered[:2]
                weight_per_alpha = 1.0 / len(alpha_candidates)
                
                for item in alpha_candidates:
                    results.append({
                        "ticker": item["ticker"],
                        "allocated_amount": round(alpha_amount * weight_per_alpha, 2),
                        "reason": f"AI Discovery - {item['reason']}",
                        "source": "ticker_discovery"
                    })
    except Exception:
        pass

    return results

async def main():
    parser = argparse.ArgumentParser(description="Analyze and suggest deployment for excess cash.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    args = parser.parse_args()
    
    result = await cash_deployment(args.user_id)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
