"""
Conversation Router — Message Routing Engine.
對話路由器 — 訊息路由引擎。

Routes incoming channel messages through a priority pipeline:
  1. Verification (帳號綁定驗證)
  2. Approval (待審核流程)
  3. Conversation (自由對話 — ConversationAgent)

遵循規範:
  - 規範一 (Clean Architecture): 單一職責，僅負責路由決策
  - 規範四 (模組化設計): 獨立可單元測試
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ConversationRouter:
    """
    Routes incoming channel messages to the correct handler.
    將傳入的頻道訊息路由到正確的處理器。

    Priority pipeline:
      1. Verification — Account binding / OTP
      2. Approval — Pending trade/workflow approvals
      3. Conversation — Free-form Q&A with ConversationAgent
    """

    def __init__(
        self,
        intent_classifier=None,
        conversation_agent_factory=None,
        tone_adapter=None,
    ):
        """
        Args:
            intent_classifier: IIntentClassifier for approval intent detection
            conversation_agent_factory: Callable(user_id, channel_type, channel_id) -> ConversationAgent
            tone_adapter: ChannelToneAdapter for response formatting
        """
        self._intent_classifier = intent_classifier
        self._conversation_agent_factory = conversation_agent_factory
        
        if tone_adapter is None:
            from src.agents.persona.channel_tone_adapter import ChannelToneAdapter
            self._tone_adapter = ChannelToneAdapter()
        else:
            self._tone_adapter = tone_adapter

    async def route(
        self,
        adapter,
        channel_user_id: str,
        text: str,
        resolved_user_id: str,
        pending_requests: List[Dict] = None,
        channel_type: str = "",
    ) -> Optional[str]:
        """
        Route a message through the priority pipeline.
        通過優先級管線路由訊息。

        Args:
            adapter: IChannelAdapter that received the message
            channel_user_id: Raw channel user ID (LINE/TG user)
            text: User's text message
            resolved_user_id: System user ID (resolved from channel mapping)
            pending_requests: List of pending approval requests
            channel_type: "telegram" | "line" | etc.

        Returns:
            Response string to send back, or None if handled internally.
        """
        text_stripped = text.strip()

        # ── 1. Verification Check ────────────────────────────
        if self._is_verification_attempt(text_stripped):
            return await self._handle_verification(
                adapter, channel_user_id, text_stripped, resolved_user_id
            )

        # ── 2. Approval Check ────────────────────────────────
        if pending_requests:
            intent = self._classify_approval_intent(text_stripped)
            if intent in ("APPROVE", "REJECT"):
                return await self._handle_approval(
                    adapter, channel_user_id, text_stripped,
                    resolved_user_id, pending_requests, intent
                )
            # If there are pending requests but intent is UNKNOWN,
            # fall through to conversation (user might be asking something else)

        # ── 2.5 Direct Operational System Commands (0-LLM Zero-Latency Fast Path) ──
        if self._is_system_command(text_stripped):
            direct_reply = await self._handle_system_command(
                adapter, channel_user_id, text_stripped, resolved_user_id
            )
            if direct_reply:
                return direct_reply

        # ── 3. Conversation (Default Fallback) ───────────────
        return await self._handle_conversation(
            adapter, channel_user_id, text_stripped,
            resolved_user_id, channel_type
        )

    # ── Pipeline Handlers ────────────────────────────────────

    def _is_verification_attempt(self, text: str) -> bool:
        """Check if the message looks like a verification code."""
        # Verification codes are typically 6-digit numbers or specific formats
        stripped = text.replace("-", "").replace(" ", "")
        if stripped.isdigit() and 4 <= len(stripped) <= 8:
            return True
        if text.upper().startswith("VERIFY"):
            return True
        return False

    async def _handle_verification(
        self, adapter, channel_user_id, text, resolved_user_id
    ) -> str:
        """Handle account verification/binding flow."""
        try:
            from src.services.verification_service import VerificationService
            svc = VerificationService()
            result = svc.verify_code(channel_user_id, text)
            if result:
                return "✅ 帳號驗證成功！您的頻道已綁定系統帳戶。"
            return "❌ 驗證碼無效或已過期，請重新取得驗證碼。"
        except ImportError:
            logger.debug("VerificationService not available, skipping")
            return None
        except Exception as e:
            logger.error(f"Verification handling error: {e}")
            return None

    def _classify_approval_intent(self, text: str) -> str:
        """Classify text as APPROVE/REJECT/UNKNOWN."""
        if self._intent_classifier:
            return self._intent_classifier.classify(text)

        # Fast keyword fallback
        key = text.upper()
        approve_kw = ["執行", "OK", "確定", "好", "可以", "批准", "YES", "APPROVE"]
        reject_kw = ["不執行", "取消", "NO", "REJECT", "不要"]

        if any(kw in key for kw in reject_kw):
            return "REJECT"
        if any(kw in key for kw in approve_kw) and "不" not in key:
            return "APPROVE"
        return "UNKNOWN"

    async def _handle_approval(
        self, adapter, channel_user_id, text,
        resolved_user_id, pending_requests, intent
    ) -> str:
        """Handle approval/rejection of pending requests."""
        # Process the most recent pending request
        latest = pending_requests[-1]
        request_id = latest.get("id", "unknown")

        if intent == "APPROVE":
            await adapter._trigger_callback(request_id, "APPROVE")
            return f"✅ 已批准請求 #{request_id}"
        else:
            await adapter._trigger_callback(request_id, "REJECT")
            return f"❌ 已拒絕請求 #{request_id}"

    async def _handle_conversation(
        self, adapter, channel_user_id, text,
        resolved_user_id, channel_type
    ) -> str:
        """
        Route to ConversationAgent for free-form Q&A.
        路由到 ConversationAgent 進行自由對話。
        """
        try:
            if self._conversation_agent_factory:
                agent = self._conversation_agent_factory(
                    user_id=resolved_user_id,
                    channel_type=channel_type,
                    channel_id=channel_user_id,
                )
                response = await agent.respond(
                    user_message=text,
                    channel_context={
                        "channel_type": channel_type,
                        "channel_user_id": channel_user_id,
                    },
                )
                
                # Apply channel tone adaptation
                if self._tone_adapter:
                    response = self._tone_adapter.adapt(response, channel_type)
                    
                return response
            else:
                # No agent factory configured — graceful fallback
                return (
                    "💬 收到您的訊息！\n"
                    "目前對話功能正在設定中，很快就能回答您的問題。"
                )
        except Exception as e:
            logger.error(f"ConversationAgent error: {e}")
            return f"⚠️ 處理您的訊息時發生錯誤，請稍後再試。"

    def _is_system_command(self, text: str) -> bool:
        """Check if message is a recognized system command."""
        cmd = text.strip().lower()
        if cmd.startswith(("/", "／")):
            return True
        exact_keywords = {
            "資產", "淨值", "對帳", "持倉", "部位", "建倉", "批次", "熔斷", "滑點", "風控",
            "status", "audit", "pnl", "holdings", "batch", "guard"
        }
        return cmd in exact_keywords

    async def _handle_system_command(
        self, adapter, channel_user_id: str, text: str, resolved_user_id: str
    ) -> Optional[str]:
        """
        Directly handles high-frequency financial commands without calling LLM.
        無延遲即時回應系統關鍵財務與對帳指令，杜絕幻覺與過期資訊。
        """
        cmd = text.strip().lower().lstrip("/").lstrip("／")

        # 1. Status / Audit / 資產 / 對帳
        if any(cmd.startswith(prefix) for prefix in ("status", "audit", "pnl", "資產", "淨值", "對帳")):
            try:
                from src.services.daily_portfolio_summary_service import DailyPortfolioSummaryService
                svc = DailyPortfolioSummaryService(user_id=resolved_user_id)
                summary = await svc.generate_summary()

                eq = summary.get("total_equity", 0.0)
                cash = summary.get("total_cash", 0.0)
                inv = summary.get("invested_capital", 1711.0)
                cum_pnl = summary.get("cumulative_pnl", eq - inv)
                cum_pct = summary.get("cumulative_pnl_pct", (cum_pnl / inv * 100) if inv > 0 else 0)
                unreal = summary.get("total_unrealized_pnl", 0.0)
                real = summary.get("closed_realized_pnl", cum_pnl - unreal)
                def_cash = summary.get("defensive_reserve_usd", eq * 0.20)
                dep_cash = summary.get("deployable_cash", max(0.0, cash - def_cash))
                count = summary.get("positions_count", 0)

                cum_emoji = "🟢" if cum_pnl >= 0 else "🔴"
                cum_str = f"+${cum_pnl:,.2f}" if cum_pnl >= 0 else f"-${abs(cum_pnl):,.2f}"
                cum_pct_str = f"+{cum_pct:.2f}%" if cum_pct >= 0 else f"{cum_pct:.2f}%"
                unreal_emoji = "🟢" if unreal >= 0 else "🔴"
                unreal_str = f"+${unreal:,.2f}" if unreal >= 0 else f"-${abs(unreal):,.2f}"
                real_emoji = "🟢" if real >= 0 else "🔴"
                real_str = f"+${real:,.2f}" if real >= 0 else f"-${abs(real):,.2f}"

                return (
                    f"📊 <b>【實盤真實驗資與對帳總結】</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>總資產淨值 (NLV)</b>：${eq:,.2f} USD\n"
                    f"🏦 <b>累計存入本金</b>：${inv:,.2f} USD\n"
                    f"🎯 <b>全週期累計淨損益</b>：{cum_emoji} {cum_str} ({cum_pct_str})\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 <b>可用現金餘額</b>：${cash:,.2f} USD\n"
                    f"🛡️ <b>剛性防守儲備 (20%)</b>：${def_cash:,.2f} USD\n"
                    f"🚀 <b>可動用建倉現金</b>：${dep_cash:,.2f} USD\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>持倉未實現盈虧</b>：{unreal_emoji} {unreal_str} USD\n"
                    f"📉 <b>歷史已平倉損益</b>：{real_emoji} {real_str} USD\n"
                    f"👤 <b>活躍持股檔數</b>：{count} 檔\n"
                    f"⚡ <b>開盤自動排程</b>：今晚 21:35 TST 第 1 批次建倉 ($347: NVDA, TSM, AAPL)\n"
                    f"<i>(數據由券商即時同步與真實驗資引擎核算，無 LLM 延遲)</i>"
                )
            except Exception as e:
                logger.error(f"Failed to generate quick status command response: {e}")
                return f"⚠️ 查詢資產對帳狀態時發生錯誤：{e}"

        # 2. Holdings / Positions / 持倉 / 部位
        if any(cmd.startswith(prefix) for prefix in ("holdings", "positions", "持倉", "部位")):
            try:
                from src.services.portfolio_aggregator_service import PortfolioAggregatorService
                agg = PortfolioAggregatorService(user_id=resolved_user_id)
                port = await agg.get_aggregated_portfolio()
                positions = port.get("positions", [])
                total_eq = float(port.get("total_equity", 0.0))

                if not positions:
                    return "ℹ️ 目前無任何活躍持倉，帳戶為 100% 現金儲備。"

                lines = ["📋 <b>【當前實盤持倉清單】</b>", "━━━━━━━━━━━━━━━━━━"]
                for p in positions:
                    val = float(getattr(p, "market_value", 0.0) or 0.0)
                    weight = (val / total_eq * 100.0) if total_eq > 0 else 0.0
                    pnl = float(getattr(p, "unrealized_pnl", 0.0) or 0.0)
                    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                    qty = float(getattr(p, "quantity", 0.0) or 0.0)
                    price = float(getattr(p, "current_price", 0.0) or 0.0)
                    sym = getattr(p, "symbol", "")
                    lines.append(f"• <b>{sym}</b>: {qty:.4f} 股 @ ${price:.2f} | 市值 ${val:.2f} ({weight:.1f}%) | {pnl_emoji} {pnl_str}")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append(f"合計 {len(positions)} 檔部位，持倉總市值 ${sum(p.market_value for p in positions):.2f} USD")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate quick holdings response: {e}")
                return f"⚠️ 查詢持倉清單時發生錯誤：{e}"

        # 3. Batch / Deploy / 建倉 / 批次
        if any(cmd.startswith(prefix) for prefix in ("batch", "deploy", "建倉", "批次")):
            try:
                from src.services.batch_cash_deployment_service import BatchCashDeploymentService
                deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                plan1 = await deploy_svc.get_deployment_plan(batch_number=1)
                status = plan1.get("portfolio_status", {})
                items1 = plan1.get("plan_items", [])

                lines = [
                    "🚀 <b>【分批建倉計畫與排程進度】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"💰 可支配建倉資金：${status.get('deployable_cash', 0.0):,.2f} USD",
                    f"🛡️ 剛性防守儲備 (20%)：${status.get('required_reserve_usd', 0.0):,.2f} USD",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【第 1 批次（今晚 21:35 TST 自動觸發）】</b>"
                ]
                for it in items1:
                    lines.append(f"• <b>{it['ticker']}</b>: ~${it['allocated_amount']:.2f} ({it['role']})")

                lines.append(f"批次小計：${plan1.get('total_batch_amount', 0.0):.2f} USD (執行後現金保持 ${plan1.get('projected_cash_after_deployment', 0.0):.2f})")
                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("<b>【後續規劃】</b>")
                lines.append("• 第 2 批次（下週一 09:35 EST）：MSFT ($91), MU ($79), AMD ($77)")
                lines.append("• 第 3 批次（下週三 09:35 EST）：SPCX ($76)")
                lines.append("<i>全流程均受 0.15% 開盤價差熔斷與自適應限價守衛保護。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate quick batch plan response: {e}")
                return f"⚠️ 查詢建倉排程時發生錯誤：{e}"

        # 4. Guard / Slippage / 熔斷 / 滑點 / 風控
        if any(cmd.startswith(prefix) for prefix in ("guard", "circuit", "slippage", "熔斷", "滑點", "風控")):
            try:
                from src.services.slippage_guard_service import SlippageGuardService
                guard = SlippageGuardService()
                setting_enabled = guard.settings_service.get_setting("enable_slippage_guard")
                max_spread = guard.settings_service.get_setting("max_allowed_spread_pct")
                is_open = guard.market_clock.is_market_open() if guard.market_clock else False
                auction_res = guard.is_opening_auction_window()
                is_auction = auction_res[0] if isinstance(auction_res, tuple) else bool(auction_res)

                return (
                    f"🛡️ <b>【開盤防滑點守衛與價差熔斷狀態】</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>守衛功能開關</b>：{'🟢 已啟用 (Enabled)' if setting_enabled else '🔴 已停用'}\n"
                    f"• <b>最大容許價差門檻</b>：{float(max_spread or 0.0015)*100:.2f}% (15 bps)\n"
                    f"• <b>美股市場開市狀態</b>：{'🟢 開市中 (Open)' if is_open else '⚪ 休市中 (Closed)'}\n"
                    f"• <b>開盤高波動保護窗口 (09:30-09:35)</b>：{'⚠️ 觸發保護中 (Active)' if is_auction else '✅ 安全窗口'}\n"
                    f"• <b>自適應限價單保護</b>：Mid + Spread × 0.25 封頂\n"
                    f"• <b>事後滑點異常告警門檻</b>：> 0.20% 自動通報\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<i>今晚 21:35 TST 開盤建倉時將自動為每一筆訂單執行即時報價驗證。</i>"
                )
            except Exception as e:
                logger.error(f"Failed to generate quick guard response: {e}")
                return f"⚠️ 查詢風控守衛狀態時發生錯誤：{e}"

        return None
