"""
Skill Implementation: run_sentinel_check
技能實作：Sentinel 即時市場巡邏

Extracted from: SentinelService.process_tick()
Reusable in: Heartbeat, Event, Channel Q&A
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def run_sentinel_check(user_id: str) -> str:
    """
    Trigger a Sentinel patrol scan for the specified user.
    觸發指定使用者的 Sentinel 巡邏掃描。

    This is an async skill because SentinelService operations
    are inherently async (API calls, market data fetching).

    Returns a formatted summary of the scan results.
    """
    try:
        from src.services.sentinel_service import SentinelService

        sentinel = SentinelService(user_id=user_id)

        # Run the tick — this performs market scan, anomaly detection, etc.
        result = await sentinel.process_tick()

        if not result:
            return "🟢 **Sentinel 巡邏完成**\n目前無異常訊號，市場狀態正常。"

        # Format the result
        if isinstance(result, dict):
            alerts = result.get("alerts", [])
            risk_level = result.get("risk_level", "normal")

            risk_emoji = {
                "normal": "🟢",
                "elevated": "🟡",
                "high": "🔴",
                "critical": "⛔",
            }.get(risk_level, "⚪")

            lines = [
                f"{risk_emoji} **Sentinel 巡邏報告**",
                f"風險等級: {risk_level.upper()}",
            ]

            if alerts:
                lines.append(f"\n⚠️ **偵測到 {len(alerts)} 個警報:**")
                for alert in alerts[:5]:  # Cap at 5
                    lines.append(f"  • {alert}")

            return "\n".join(lines)

        return f"🟢 **Sentinel 巡邏完成**\n{str(result)[:500]}"

    except Exception as e:
        logger.error(f"run_sentinel_check failed: {e}")
        return f"⚠️ Sentinel 巡邏失敗: {e}"
