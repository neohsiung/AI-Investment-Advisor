"""
Skill Implementation: get_user_holdings
技能實作：取得使用者目前持股清單

Extracted from: BaseWorkflow.collect_data() + WeeklyWorkflow holdings_map
Reusable in: Daily, Weekly, Event, Channel Q&A, Council
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def get_user_holdings(user_id: str) -> str:
    """
    Fetch and format user's current portfolio holdings.
    取得並格式化使用者目前的投資組合持股。

    Returns a formatted string showing all positions.
    """
    try:
        from src.services.transaction_service import TransactionService

        svc = TransactionService()
        holdings_map = svc.get_holdings_map(user_id)

        if not holdings_map:
            return "📭 目前沒有持股 (No current holdings)"

        # Format holdings
        lines = [f"📋 **投資組合持股 ({len(holdings_map)} 檔)**\n"]

        total_value = 0.0
        for ticker, data in sorted(holdings_map.items()):
            qty = data.get("quantity", 0)
            avg_cost = data.get("avg_cost", 0)
            current_value = data.get("market_value", qty * avg_cost)
            total_value += current_value

            # Format each position
            lines.append(
                f"• **{ticker}**: {qty} 股 | "
                f"均價 ${avg_cost:.2f} | "
                f"市值 ${current_value:,.2f}"
            )

        lines.append(f"\n💰 **持股總市值**: ${total_value:,.2f}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"get_user_holdings failed: {e}")
        return f"⚠️ 持股資料取得失敗: {e}"


def get_user_holdings_raw(user_id: str) -> List[Dict[str, Any]]:
    """
    Fetch raw holdings data (for programmatic use by other skills/workflows).
    取得原始持股資料（供其他技能/工作流程式化使用）。
    """
    try:
        from src.services.transaction_service import TransactionService

        svc = TransactionService()
        holdings_map = svc.get_holdings_map(user_id)

        return [
            {"symbol": ticker, "quantity": data.get("quantity", 0), **data}
            for ticker, data in holdings_map.items()
        ]
    except Exception as e:
        logger.error(f"get_user_holdings_raw failed: {e}")
        return []
