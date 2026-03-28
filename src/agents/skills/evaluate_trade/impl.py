"""
Skill Implementation: evaluate_trade
技能實作：評估並執行交易指令

Extracted from: AutomatedTradingService.evaluate_and_execute_trade()
Reusable in: Daily, Weekly, Event, Channel (with Approval)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def evaluate_trade(
    user_id: str,
    ticker: str,
    action: str,
    quantity: float,
    confidence_score: float = 50.0,
    rationale: str = "Agent Signal",
) -> str:
    """
    Evaluate and execute a trade order through the AutomatedTradingService.
    通過 AutomatedTradingService 評估並執行交易指令。

    This goes through the full risk-check pipeline:
    1. Pre-trade risk evaluation
    2. Broker integration (if enabled)
    3. Transaction recording
    4. Notification

    Args:
        user_id: User executing the trade
        ticker: Stock ticker symbol
        action: "BUY" | "SELL" | "HOLD"
        quantity: Number of shares
        confidence_score: AI confidence (0-100)
        rationale: Explanation for the trade

    Returns:
        Formatted trade result
    """
    if action.upper() == "HOLD":
        return f"⏸️ **{ticker}**: 維持觀望 — {rationale}"

    try:
        from src.services.automated_trading_service import AutomatedTradingService

        auto_trade_svc = AutomatedTradingService()

        result = await auto_trade_svc.evaluate_and_execute_trade(
            ticker=ticker,
            action=action.upper(),
            quantity=quantity,
            confidence_score=confidence_score,
            rationale=rationale,
            user_id=user_id,
        )

        # Format result
        action_emoji = "🟢" if action.upper() == "BUY" else "🔴"

        if isinstance(result, dict):
            status = result.get("status", "unknown")
            msg = result.get("message", "")
            return (
                f"{action_emoji} **{action.upper()} {ticker}** x{quantity}\n"
                f"狀態: {status}\n"
                f"信心分數: {confidence_score:.0f}%\n"
                f"理由: {rationale}\n"
                f"{msg}"
            )

        return (
            f"{action_emoji} **{action.upper()} {ticker}** x{quantity}\n"
            f"結果: {str(result)[:300]}"
        )

    except Exception as e:
        logger.error(f"evaluate_trade failed: {e}")
        return f"⚠️ 交易執行失敗 ({ticker} {action}): {e}"
