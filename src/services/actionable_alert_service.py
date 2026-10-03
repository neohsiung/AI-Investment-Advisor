"""
Actionable Alert Hub Service (P3)
=================================
Coordinates real-time, interactive notifications across multi-channel adapters
(Telegram, Slack, Discord, Email). Provides actionable buttons for Human-in-the-Loop
control over critical trading events, including institutional support breakdowns,
circuit-breaker tripping, shadow ledger graduation/eviction, and slippage anomalies.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from src.utils.logger import setup_logger
from src.config.owner import resolve_user_id

logger = setup_logger("ActionableAlertHubService")


class ActionableAlertHubService:
    """
    Actionable Alert Hub Service.
    Dispatches rich notifications with inline action buttons and executes
    interactive callbacks across Telegram, Slack, and other channels.
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id or resolve_user_id()

    def _get_notification_service(self):
        from src.services.settings_service import SettingsService
        from src.services.notification_service import NotificationService
        ss = SettingsService(user_id=self.user_id)
        return NotificationService.create_with_settings(settings_service=ss, user_id=self.user_id)

    async def dispatch_support_breakdown_alert(
        self,
        ticker: str,
        current_price: float,
        support_price: float,
        breakdown_pct: float,
        unrealized_pnl_pct: Optional[float] = None,
        position_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Dispatched when an active position falls below its institutional cost basis / support line.
        Provides immediate 1-tap Close, Pause Trading, or Dismiss actions.
        """
        sym = ticker.upper().strip()
        pnl_str = f"{unrealized_pnl_pct:+.2f}%" if unrealized_pnl_pct is not None else "N/A"
        val_str = f"${position_value:,.2f}" if position_value is not None else "N/A"

        title = f"🚨 跌破主力支撐警報：{sym}"
        content = (
            f"標的 <b>{sym}</b> 已跌破機構主力籌碼防線！\n\n"
            f"• <b>當前市價</b>：${current_price:.2f}\n"
            f"• <b>主力支撐價</b>：${support_price:.2f}\n"
            f"• <b>跌破幅度</b>：-{abs(breakdown_pct):.2f}%\n"
            f"• <b>部位未實現損益</b>：{pnl_str} (價值: {val_str})\n\n"
            f"系統建議立即平倉鎖定利潤或防止虧損擴大。請點擊下方按鈕執行操作："
        )

        # Telegram callback_data limit is 64 bytes — keep compact!
        actions = [
            {"label": "🚨 一鍵平倉 (Close)", "data": f"action=close_pos&ticker={sym}", "key": "close_pos"},
            {"label": "⏸️ 暫停交易 (Pause)", "data": "action=pause_trading", "key": "pause_trading"},
            {"label": "👀 忽略維持 (Dismiss)", "data": "action=dismiss", "key": "dismiss"},
        ]

        logger.warning(
            "ActionableAlertHub: Dispatching support breakdown alert for %s (price=%.2f, support=%.2f)",
            sym, current_price, support_price,
        )

        noti_svc = self._get_notification_service()
        return await noti_svc.notify_all(
            title=title,
            content=content,
            user_id=self.user_id,
            actions=actions,
            category="trading",
        )

    async def dispatch_protection_breached_alert(
        self,
        rule_name: str,
        reason: str,
        ticker: Optional[str] = None,
        consecutive_losses: Optional[int] = None,
        drawdown_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Dispatched when trading protections or circuit breakers halt trading activity.
        Provides 1-tap Reset or Keep Paused actions.
        """
        ticker_part = f" [{ticker.upper()}]" if ticker else ""
        title = f"🛡️ 風控保護機制觸發{ticker_part}：{rule_name}"

        details = []
        if consecutive_losses is not None:
            details.append(f"• 連續虧損筆數：{consecutive_losses}")
        if drawdown_pct is not None:
            details.append(f"• 歷史回撤幅度：{drawdown_pct:.2f}%")
        details_str = ("\n" + "\n".join(details)) if details else ""

        content = (
            f"系統已自動觸發交易保護機制，暫停新單下發以防範風險擴大！\n\n"
            f"• <b>保護規則</b>：{rule_name}\n"
            f"• <b>觸發原因</b>：{reason}{details_str}\n\n"
            f"若您已評估市場狀況並確認安全，可點選下方按鈕重設保護或維持暫停："
        )

        actions = [
            {"label": "🔄 重設熔斷 (Reset)", "data": "action=reset_protection", "key": "reset_protection"},
            {"label": "⏸️ 維持暫停 (Keep Paused)", "data": "action=dismiss", "key": "dismiss"},
        ]

        logger.warning(
            "ActionableAlertHub: Dispatching protection breached alert (%s: %s)",
            rule_name, reason,
        )

        noti_svc = self._get_notification_service()
        return await noti_svc.notify_all(
            title=title,
            content=content,
            user_id=self.user_id,
            actions=actions,
            category="trading",
        )

    async def dispatch_shadow_graduation_alert(
        self,
        ticker: str,
        graduated: bool,
        metrics: Dict[str, Any],
        eval_days: int,
        unrealized_pnl_pct: float,
        max_drawdown_pct: float,
        support_breached: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatched when a shadow candidate completes evaluation (graduation or failure).
        """
        sym = ticker.upper().strip()
        if graduated:
            title = f"🎉 影子交易考核合格：{sym} 晉升實盤！"
            content = (
                f"標的 <b>{sym}</b> 已順利通過影子交易軌道考核，正式晉升為實盤活躍自選股！\n\n"
                f"• <b>觀察天數</b>：{eval_days} 個交易日\n"
                f"• <b>累積浮動報酬</b>：{unrealized_pnl_pct:+.2f}%\n"
                f"• <b>峰值最大回撤</b>：{max_drawdown_pct:.2f}%\n"
                f"• <b>主力成本防守</b>：✅ 守穩未跌破\n\n"
                f"後續該標的之交易訊號將由實盤券商自動執行。"
            )
            actions = [
                {"label": "📊 檢視活躍池 (Universe)", "data": "action=view_universe", "key": "view_universe"},
                {"label": "👌 確認知悉 (Dismiss)", "data": "action=dismiss", "key": "dismiss"},
            ]
        else:
            breach_str = "❌ 已跌破" if support_breached else "✅ 守穩"
            title = f"⚠️ 影子交易考核未通過：{sym} 淘汰降級"
            content = (
                f"標的 <b>{sym}</b> 未能通過影子交易軌道考核，已自候選名單淘汰！\n\n"
                f"• <b>累積觀察天數</b>：{eval_days} 天\n"
                f"• <b>累積浮動報酬</b>：{unrealized_pnl_pct:+.2f}%\n"
                f"• <b>峰值最大回撤</b>：{max_drawdown_pct:.2f}%\n"
                f"• <b>主力成本防守</b>：{breach_str}\n\n"
                f"實盤真金資本全程受到保護，未承擔任何虧損。"
            )
            actions = [
                {"label": "🗑️ 確認淘汰 (Evict)", "data": f"action=confirm_eviction&ticker={sym}", "key": "confirm_evict"},
                {"label": "👌 確認知悉 (Dismiss)", "data": "action=dismiss", "key": "dismiss"},
            ]

        logger.info(
            "ActionableAlertHub: Dispatching shadow graduation alert for %s (graduated=%s)",
            sym, graduated,
        )

        noti_svc = self._get_notification_service()
        return await noti_svc.notify_all(
            title=title,
            content=content,
            user_id=self.user_id,
            actions=actions,
            category="trading",
        )

    async def dispatch_large_slippage_alert(
        self,
        ticker: str,
        expected_price: float,
        executed_price: float,
        slippage_pct: float,
        action: str = "BUY",
    ) -> Dict[str, Any]:
        """
        Dispatched when execution slippage exceeds the configured tolerance threshold.
        """
        sym = ticker.upper().strip()
        title = f"⚠️ 執行滑價異常警告：{sym}"
        content = (
            f"標的 <b>{sym}</b> 的 {action} 訂單成交價格出現較大滑價！\n\n"
            f"• <b>預期價格</b>：${expected_price:.2f}\n"
            f"• <b>實施成交價</b>：${executed_price:.2f}\n"
            f"• <b>滑價偏差</b>：{slippage_pct:.2f}%\n\n"
            f"請留意市場流動性或券商撮合品質。如需干預，可點選下方按鈕暫停交易："
        )
        actions = [
            {"label": "⏸️ 暫停交易 (Pause)", "data": "action=pause_trading", "key": "pause_trading"},
            {"label": "✅ 確認知悉 (Dismiss)", "data": "action=dismiss", "key": "dismiss"},
        ]

        logger.warning(
            "ActionableAlertHub: Dispatching large slippage alert for %s (slippage=%.2f%%)",
            sym, slippage_pct,
        )

        noti_svc = self._get_notification_service()
        return await noti_svc.notify_all(
            title=title,
            content=content,
            user_id=self.user_id,
            actions=actions,
            category="trading",
        )

    async def execute_action(
        self,
        action_name: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Central execution engine for interactive callback actions from Telegram, Slack, or Web UI.
        """
        params = params or {}
        action = action_name.lower().strip()
        logger.info(
            "ActionableAlertHub: Executing action '%s' for user %s with params %s",
            action, self.user_id, params,
        )

        from src.services.settings_service import SettingsService
        ss = SettingsService(user_id=self.user_id)

        if action == "pause_trading":
            ss.save_setting("ai_trading_enabled", "false")
            return {
                "ok": True,
                "action": action,
                "message": "⏸️ 已成功暫停 AI 自動交易。所有新開倉訊號已被阻斷。",
            }

        elif action == "resume_trading":
            ss.save_setting("ai_trading_enabled", "true")
            return {
                "ok": True,
                "action": action,
                "message": "▶️ 已成功恢復 AI 自動交易。",
            }

        elif action == "close_pos":
            ticker = params.get("ticker", "").upper().strip()
            if not ticker:
                return {"ok": False, "action": action, "message": "❌ 未指定平倉標的代號 (Ticker)"}

            try:
                # 1. Check if broker provides direct position lookup & close (e.g. mocked in tests)
                from src.services.etoro_service import EtoroService
                etoro = EtoroService(user_id=self.user_id)
                closed_count = 0
                if hasattr(etoro, "get_portfolio"):
                    port = etoro.get_portfolio()
                    positions = [p for p in (port.get("positions", []) if isinstance(port, dict) else []) if str(p.get("ticker", "")).upper() == ticker]
                    for pos in positions:
                        pos_id = pos.get("id") or pos.get("position_id")
                        if pos_id and hasattr(etoro, "close_position"):
                            etoro.close_position(position_id=pos_id)
                            closed_count += 1

                if closed_count > 0:
                    return {
                        "ok": True,
                        "action": action,
                        "ticker": ticker,
                        "message": f"🚨 已成功送出 {ticker} 市價平倉指令（共平倉 {closed_count} 筆部位）。",
                    }

                # 2. Unified execution via AutomatedTradingService
                from src.services.automated_trading_service import AutomatedTradingService
                auto_svc = AutomatedTradingService()
                res = await auto_svc.evaluate_and_execute_trade(
                    user_id=self.user_id,
                    ticker=ticker,
                    action="SELL",
                    confidence_score=10.0,
                    rationale="Interactive Alert Hub 1-tap manual emergency close",
                )
                status_str = res.get("status") or ("success" if res.get("success") else "submitted")
                return {
                    "ok": True,
                    "action": action,
                    "ticker": ticker,
                    "message": f"🚨 已為 {ticker} 送出緊急平倉單 (執行結果: {status_str})。",
                }
            except Exception as e:
                logger.error("Failed to close position for %s: %s", ticker, e, exc_info=True)
                return {"ok": False, "action": action, "ticker": ticker, "message": f"❌ 平倉失敗: {str(e)}"}

        elif action == "reset_protection":
            # Re-enable trading and reset any soft halts
            ss.save_setting("ai_trading_enabled", "true")
            return {
                "ok": True,
                "action": action,
                "message": "🔄 風控保護機制已手動重設，AI 交易已恢復就緒。",
            }

        elif action == "confirm_eviction":
            ticker = params.get("ticker", "").upper().strip()
            if not ticker:
                return {"ok": False, "action": action, "message": "❌ 未指定淘汰標的代號"}

            try:
                from src.repositories.ticker_universe_repository import TickerUniverseRepository
                repo = TickerUniverseRepository()
                repo.upsert(self.user_id, ticker, status="removed")
                repo.add_log(
                    self.user_id,
                    ticker,
                    "actionable_alert_evict",
                    "ActionableAlertHubService",
                    reasoning="User confirmed eviction via interactive alert button",
                    old_status="candidate",
                    new_status="removed",
                )
                return {
                    "ok": True,
                    "action": action,
                    "ticker": ticker,
                    "message": f"🗑️ 已確認將 {ticker} 自標的池中淘汰並封存紀錄。",
                }
            except Exception as e:
                logger.error("Failed to evict ticker %s: %s", ticker, e)
                return {"ok": False, "action": action, "ticker": ticker, "message": f"❌ 淘汰失敗: {str(e)}"}

        elif action == "view_universe":
            try:
                from src.repositories.ticker_universe_repository import TickerUniverseRepository
                repo = TickerUniverseRepository()
                active = repo.get_all(self.user_id, status="active")
                symbols = [r["ticker"] for r in active]
                msg = f"📊 <b>當前活躍實盤標的池 ({len(symbols)} 檔)</b>：\n" + ", ".join(symbols)
                return {"ok": True, "action": action, "message": msg}
            except Exception as e:
                return {"ok": False, "action": action, "message": f"❌ 查詢標的池失敗: {str(e)}"}

        elif action == "dismiss":
            return {"ok": True, "action": action, "message": "👌 警報已確認知悉。"}

        else:
            logger.warning("Unrecognized action '%s' received", action)
            return {"ok": False, "action": action, "message": f"❓ 未知操作指令: {action}"}
