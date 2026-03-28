"""
Skill Implementation: get_macro_summary
技能實作：取得即時宏觀經濟指標摘要

Extracted from: DailyWorkflow.synthesize_results() / WeeklyWorkflow.run_weekly_cycle()
Reusable in: Daily, Weekly, Event, Channel Q&A
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_macro_summary(user_id: str) -> str:
    """
    Fetch and format macro economic indicators.
    取得並格式化宏觀經濟指標。

    Returns a formatted string suitable for both Agent context injection
    and direct user-facing display on channels.

    Indicators:
      - VIX (恐慌指數)
      - SPY (大盤指標)
      - 10Y-2Y Yield Spread (殖利率曲線)
      - Fed Funds Rate (聯邦基金利率)
    """
    try:
        from src.services.market_data_service import MarketDataService

        svc = MarketDataService(user_id=user_id)
        macro_data = svc.get_macro_data()

        # Extract indicators (handle nested or flat structures)
        market_ind = macro_data.get("market_indicators", {})
        economics = macro_data.get("economics", {})

        vix = market_ind.get("^VIX", macro_data.get("^VIX", "N/A"))
        spy = market_ind.get("SPY", macro_data.get("SPY", "N/A"))

        spread_data = economics.get("10Y2Y_Spread", {})
        spread = (
            spread_data.get("value", "N/A")
            if isinstance(spread_data, dict)
            else spread_data
        )

        fed_rate_data = economics.get("FedFundsRate", {})
        fed_rate = (
            fed_rate_data.get("value", "N/A")
            if isinstance(fed_rate_data, dict)
            else fed_rate_data
        )

        # Format VIX interpretation
        vix_emoji = "🟢"
        vix_label = "低波動"
        try:
            vix_val = float(str(vix).replace(",", ""))
            if vix_val > 30:
                vix_emoji = "🔴"
                vix_label = "高度恐慌"
            elif vix_val > 20:
                vix_emoji = "🟡"
                vix_label = "中度波動"
        except (ValueError, TypeError):
            pass

        summary = (
            f"📊 **宏觀經濟指標摘要 (Macro Summary)**\n\n"
            f"{vix_emoji} **VIX (恐慌指數)**: {vix} — {vix_label}\n"
            f"📈 **SPY (S&P 500)**: {spy}\n"
            f"📉 **10Y-2Y Spread**: {spread}\n"
            f"🏦 **Fed Funds Rate**: {fed_rate}\n"
        )

        return summary

    except Exception as e:
        logger.error(f"get_macro_summary failed: {e}")
        return f"⚠️ 宏觀數據取得失敗: {e}"
