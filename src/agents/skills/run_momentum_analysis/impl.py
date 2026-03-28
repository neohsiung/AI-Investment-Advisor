"""
Skill Implementation: run_momentum_analysis
技能實作：動能分析 (RSI, MACD, Volume)

Extracted from: DailyWorkflow agent task execution
Reusable in: Daily, Weekly, Event, Channel Q&A
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def run_momentum_analysis(
    user_id: str,
    tickers: Optional[List[str]] = None,
) -> str:
    """
    Run technical momentum analysis on specified or user-held tickers.
    對指定或使用者持有的標的執行技術面動能分析。

    Delegates to the Momentum Agent with appropriate context.

    Args:
        user_id: User ID for portfolio context
        tickers: Optional list of tickers. Defaults to user's holdings.

    Returns:
        Formatted momentum analysis report
    """
    try:
        # Resolve tickers if not provided
        if not tickers:
            from src.agents.skills.get_user_holdings.impl import (
                get_user_holdings_raw,
            )

            holdings = get_user_holdings_raw(user_id)
            tickers = [h["symbol"] for h in holdings]

        if not tickers:
            return "📭 沒有可分析的標的 (No tickers to analyze)"

        # Fetch market data for all tickers
        from src.services.market_data_service import MarketDataService

        market_svc = MarketDataService(user_id=user_id)

        results = []
        for ticker in tickers[:10]:  # Cap at 10 to avoid timeout
            try:
                data = market_svc.get_stock_data(ticker)
                if not data:
                    results.append(f"• **{ticker}**: ⚠️ 數據不可用")
                    continue

                price = data.get("price", "N/A")
                change_pct = data.get("change_percent", 0)
                rsi = data.get("rsi", "N/A")
                volume_ratio = data.get("volume_ratio", 1.0)

                # Interpret signals
                momentum_signal = _interpret_momentum(rsi, change_pct, volume_ratio)

                results.append(
                    f"• **{ticker}** ${price} ({change_pct:+.2f}%) | "
                    f"RSI: {rsi} | Vol Ratio: {volume_ratio:.1f}x | "
                    f"{momentum_signal}"
                )
            except Exception as e:
                results.append(f"• **{ticker}**: ⚠️ {e}")

        header = f"🔬 **動能分析 ({len(tickers)} 檔)**\n"
        return header + "\n".join(results)

    except Exception as e:
        logger.error(f"run_momentum_analysis failed: {e}")
        return f"⚠️ 動能分析失敗: {e}"


def _interpret_momentum(rsi, change_pct, volume_ratio) -> str:
    """Generate human-readable momentum interpretation."""
    try:
        rsi_val = float(str(rsi))
    except (ValueError, TypeError):
        return "📊 訊號不明確"

    if rsi_val > 70:
        signal = "🔴 超買"
    elif rsi_val < 30:
        signal = "🟢 超賣"
    elif rsi_val > 60:
        signal = "🟡 偏多"
    elif rsi_val < 40:
        signal = "🟡 偏空"
    else:
        signal = "⚪ 中性"

    try:
        vol = float(volume_ratio)
        if vol > 2.0:
            signal += " + 量增異常"
    except (ValueError, TypeError):
        pass

    return signal
