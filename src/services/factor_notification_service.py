"""
Factor Notification Service (Option B: Multi-Channel Alerts)
===========================================================
Dispatches immediate, rich multi-channel notifications (Telegram, Slack, Email, Web, etc.)
for synthesized quantitative factor lifecycle events and live trading decisions.

Triggers:
  1. Live License Granted (Approval / Canary 14-day graduation) -> P1 / Success
  2. Circuit Breaker Tripped (Daily shadow loss <= -5% or emergency kill) -> P0 / Urgent
  3. Live Order Decision (Synthesized factor actively participating in position sizing) -> P1 / Trade Info
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from src.config.owner import resolve_user_id

logger = logging.getLogger("FactorNotificationService")


class FactorNotificationService:
    """
    Coordinates multi-channel alerts for synthesized quantitative factors.
    Strictly adheres to Constraint #0 (Fail-Silent Prevention) and multi-tenancy.
    """

    def __init__(self, user_id: Optional[str] = None, settings_service=None):
        self.user_id = resolve_user_id(user_id) if user_id else None
        self._settings_service = settings_service

    def _get_notification_service(self, user_id: str):
        """Builds a NotificationService configured with the target user's settings."""
        from src.services.notification_service import NotificationService
        from src.services.settings_service import SettingsService

        settings_svc = self._settings_service or SettingsService()
        return NotificationService.create_with_settings(
            settings_service=settings_svc,
            user_id=user_id,
        )

    def _get_active_channels(self, user_id: str) -> List[str]:
        """Queries the user's active notification channels from DB settings."""
        from src.services.notification_settings_manager import NotificationSettingsManager
        from src.services.settings_service import SettingsService

        try:
            settings_svc = self._settings_service or SettingsService()
            nsm = NotificationSettingsManager(
                settings_repo=settings_svc.settings_repo,
                user_id=user_id,
            )
            channels = nsm.get_active_notification_channels()
            return channels if channels else ["web"]
        except Exception as e:
            logger.warning(
                "Failed to query active channels for %s, falling back to ['web']: %s",
                user_id,
                e,
            )
            return ["web"]

    async def notify_factor_promoted(
        self,
        artifact_name: str,
        regime: str,
        user_id: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        approval_type: str = "manual",
    ) -> Dict[str, Any]:
        """
        Dispatches an alert when a factor is granted a live license (status ACTIVE).
        """
        target_user = resolve_user_id(user_id or self.user_id)
        metrics = metrics or {}

        sharpe = metrics.get("sharpe_ratio", "N/A")
        mdd = metrics.get("max_drawdown_pct", "N/A")
        net_ret = metrics.get("net_profit_pct", "N/A")

        if isinstance(sharpe, (int, float)):
            sharpe = f"{sharpe:.2f}"
        if isinstance(mdd, (int, float)):
            mdd = f"{mdd:.1f}%"
        if isinstance(net_ret, (int, float)):
            net_ret = f"{net_ret:.1f}%"

        promotion_source = (
            "操作者人工審定核發 (Operator Manual Approval)"
            if approval_type == "manual"
            else "14 日金絲雀灰度考核通過 (14-Day Canary Graduation)"
        )

        title = "🚀 [自主量化] 自研因子核發實盤執照 (Live License Granted)"
        content_lines = [
            f"**自研因子**：`{artifact_name}`",
            f"**目標體制**：`{regime}`",
            f"**核發途徑**：{promotion_source}",
            f"**實證回測指標**：Sharpe `{sharpe}` | MDD `{mdd}` | 淨報酬 `{net_ret}`",
            "**實盤調度機制**：已動態納入 `ConfidenceCompositorService` 置信度評分矩陣，合佔最高 15% 權重上限，基礎 4 代理人維持 85% 核心主導。",
        ]
        content = "\n".join(content_lines)

        try:
            notif_svc = self._get_notification_service(target_user)
            channels = self._get_active_channels(target_user)
            results = await notif_svc.notify_all(
                title=title,
                content=content,
                user_id=target_user,
                channels=channels,
                category="system",
            )
            logger.info("Dispatched factor promotion alert for %s via %s", artifact_name, channels)
            return {"success": True, "channels": channels, "results": results}
        except Exception as e:
            logger.warning("Failed to dispatch factor promotion alert for %s: %s", artifact_name, e)
            return {"success": False, "error": str(e)}

    async def notify_circuit_breaker_tripped(
        self,
        artifact_name: str,
        reason: str,
        user_id: Optional[str] = None,
        daily_pnl_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches an urgent alert when a factor triggers safety circuit breaker or emergency kill.
        """
        target_user = resolve_user_id(user_id or self.user_id)

        title = "🚨 [安全熔斷] 自研因子緊急下線熔斷 (Circuit Breaker Tripped)"
        content_lines = [
            f"**熔斷因子**：`{artifact_name}`",
            f"**熔斷原因**：{reason}",
        ]
        if daily_pnl_pct is not None:
            content_lines.append(f"**單日回撤表現**：`{daily_pnl_pct:.2f}%` (已達 $\\le -5.0\\%$ 剛性熔斷門檻)")

        content_lines.extend([
            "**處置措施**：因子授權已即刻註銷，狀態切換為 `REJECTED` / `KILLED`。",
            "**風控保證**：已即刻移出實盤置信度評分候選池，系統平滑恢復基礎 4 代理人標準評分。",
        ])
        content = "\n".join(content_lines)

        try:
            notif_svc = self._get_notification_service(target_user)
            channels = self._get_active_channels(target_user)
            results = await notif_svc.notify_all(
                title=title,
                content=content,
                user_id=target_user,
                channels=channels,
                category="sentinel",
            )
            logger.info("Dispatched circuit breaker alert for %s via %s", artifact_name, channels)
            return {"success": True, "channels": channels, "results": results}
        except Exception as e:
            logger.warning("Failed to dispatch circuit breaker alert for %s: %s", artifact_name, e)
            return {"success": False, "error": str(e)}

    async def notify_factor_order_decision(
        self,
        ticker: str,
        action: str,
        amount_usd: float,
        composite_score: float,
        factor_name: str,
        factor_confidence: float,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches a notification when a live order decision is influenced by active synthesized factor(s).
        """
        target_user = resolve_user_id(user_id or self.user_id)

        title = f"🤖 [實盤下單] AI 自研因子參與 {ticker} 部位配置"
        content_lines = [
            f"**下單標的與動作**：`{ticker}` — **{action.upper()}**",
            f"**分配下單金額**：`${amount_usd:.2f}`",
            f"**綜合置信度評分**：`{composite_score:.2f} / 10.0`",
            f"**參與自研因子**：`{factor_name}` (因子置信度: `{factor_confidence:.2f} / 10.0`)",
            "**權重架構說明**：自研因子合佔總權重最高 15% 上限，基礎 4 代理人維持 85% 核心比例，總權重嚴格歸一。",
        ]
        content = "\n".join(content_lines)

        try:
            notif_svc = self._get_notification_service(target_user)
            channels = self._get_active_channels(target_user)
            results = await notif_svc.notify_all(
                title=title,
                content=content,
                user_id=target_user,
                channels=channels,
                category="trading",
            )
            logger.info("Dispatched factor order decision alert for %s via %s", ticker, channels)
            return {"success": True, "channels": channels, "results": results}
        except Exception as e:
            logger.warning("Failed to dispatch factor order decision alert for %s: %s", ticker, e)
            return {"success": False, "error": str(e)}


# Singleton instance
factor_notification_service = FactorNotificationService()
