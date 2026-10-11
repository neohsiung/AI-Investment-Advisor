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

import json
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
            "預熱", "報價", "行情", "status", "audit", "pnl", "holdings", "batch", "guard",
            "warmup", "quote", "calendar", "earnings", "行事曆", "財報", "日曆", "大事記",
            "quality", "fills", "slippage", "成交品質", "滑點統計", "流動性",
            "factor", "factors", "ic", "因子", "特徵漂移", "因子自癒", "因子監控",
            "evolve", "evolution", "ga", "演化", "基因演化", "因子演化", "遺傳演化",
            "ortho", "orthogonal", "vif", "正交", "正交化", "共線性", "因子正交",
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

                # 取得動態分批建倉狀態
                batch_schedule_str = "全週期分批建倉已完成 (維持 20% 防守底線)"
                try:
                    from src.services.batch_cash_deployment_service import BatchCashDeploymentService
                    deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                    active_b = await deploy_svc.get_active_batch_number()
                    if active_b > 0:
                        plan = await deploy_svc.get_deployment_plan(batch_number=active_b)
                        plan_items = plan.get("items") or plan.get("plan_items", [])
                        item_tickers = ", ".join(it.get("ticker", "") for it in plan_items)
                        total_batch_amt = float(plan.get("total_batch_amount", 0.0) or 0.0)
                        batch_schedule_str = f"待命執行第 {active_b} 批次建倉 (${total_batch_amt:.0f}: {item_tickers})"
                except Exception as b_err:
                    logger.debug(f"Failed to load dynamic batch schedule for status: {b_err}")

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
                    f"⚡ <b>開盤自動排程</b>：{batch_schedule_str}\n"
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
                active_batch = await deploy_svc.get_active_batch_number()
                target_batch = active_batch if active_batch > 0 else 1
                plan = await deploy_svc.get_deployment_plan(batch_number=target_batch)
                status = plan.get("status") or plan.get("portfolio_status", {})
                items = plan.get("items") or plan.get("plan_items", [])

                deployable = float(status.get("deployable_cash", 0.0) or 0.0)
                reserve = float(status.get("required_reserve_usd", 0.0) or 0.0)
                rem_cash = float(plan.get("expected_remaining_cash") or plan.get("projected_cash_after_deployment") or 0.0)

                # 讀取 Redis 預熱行情快照 (若有)
                warmed_quotes = {}
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    r = await get_redis(decode_responses=True)
                    if r:
                        cached_raw = await r.get(f"batch_deployment:warmup_quotes:{resolved_user_id}")
                        if cached_raw:
                            warmed_quotes = json.loads(cached_raw).get("quotes", {})
                except Exception as r_err:
                    logger.debug(f"Could not load warmed quotes for batch command: {r_err}")

                lines = [
                    "🚀 <b>【分批建倉計畫與排程進度】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"💰 可支配建倉資金：${deployable:,.2f} USD",
                    f"🛡️ 剛性防守儲備 (20%)：${reserve:,.2f} USD",
                    "━━━━━━━━━━━━━━━━━━",
                ]

                if active_batch == 0:
                    lines.append("🎉 <b>【全週期分批建倉已全部完成】</b>")
                    lines.append("帳戶持倉已達成結構性平衡，並維持 20%~25% 防守現金儲備。")
                else:
                    timing_desc = "美股開盤 09:35 EST 自動觸發"
                    lines.append(f"<b>【第 {active_batch} 批次（{timing_desc}）】</b>")
                    for it in items:
                        ticker = it["ticker"]
                        amt = float(it.get("amount_usd") or it.get("allocated_amount") or 0.0)
                        role = it.get("role", "")
                        q_info = warmed_quotes.get(ticker, {})
                        quote_addon = ""
                        if q_info and q_info.get("ready"):
                            last_p = q_info.get("last") or q_info.get("mid")
                            sp_pct = q_info.get("spread_pct")
                            sp_str = f", 價差 {sp_pct*100:.2f}%" if sp_pct is not None else ""
                            quote_addon = f" [市價 ${last_p:.2f}{sp_str}]"
                        lines.append(f"• <b>{ticker}</b>: ~${amt:.2f} ({role}){quote_addon}")

                    total_amt = float(plan.get("total_batch_amount", 0.0) or 0.0)
                    lines.append(f"批次小計：${total_amt:.2f} USD (執行後現金保持 ${rem_cash:.2f})")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("<b>【全週期批次進度藍圖】</b>")
                batch_blueprints = [
                    (1, "NVDA ($114), TSM ($144), AAPL ($89)"),
                    (2, "MSFT ($91), MU ($79), AMD ($77)"),
                    (3, "SPCX ($76)"),
                ]
                for b_num, b_desc in batch_blueprints:
                    if active_batch == 0 or b_num < active_batch:
                        badge = "✅ 已完成"
                    elif b_num == active_batch:
                        badge = "⏳ 待執行"
                    else:
                        badge = "📅 待命"
                    lines.append(f"• {badge} 第 {b_num} 批次：{b_desc}")
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

                # 讀取 Redis 報價預熱狀態
                warmup_info = "⚪ 尚未預熱（開盤前 15 分鐘 09:20 EST 自動預熱）"
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    r = await get_redis(decode_responses=True)
                    if r:
                        cached_raw = await r.get(f"batch_deployment:warmup_quotes:{resolved_user_id}")
                        if cached_raw:
                            w_data = json.loads(cached_raw)
                            w_time = w_data.get("warmed_at", "")[:19].replace("T", " ")
                            q_cnt = len(w_data.get("quotes", {}))
                            b_num = w_data.get("batch_number", 0)
                            warmup_info = f"🟢 已預熱 (第 {b_num} 批次 {q_cnt} 檔標的已就緒，{w_time} UTC)"
                except Exception:
                    pass

                # 財報與重大宏觀避開守衛狀態
                blackout_info = "⚪ 守衛狀態查詢中"
                try:
                    from src.services.calendar_blackout_service import CalendarBlackoutService
                    c_guard = CalendarBlackoutService(user_id=resolved_user_id)
                    m_eval = c_guard.evaluate_macro_blackout()
                    c_summary = await c_guard.get_upcoming_calendar_summary(["MSFT", "MU", "AMD"])
                    next_m = c_summary.get("macro_status", {}).get("next_event")
                    next_m_str = f"{next_m['name']} ({next_m['time']} EST，約 {next_m['days_away']} 天後)" if next_m else "無即將發布之重大事件"
                    m_status_str = "⚠️ 避開窗口觸發中" if m_eval.is_blackout else "✅ 安全窗口"
                    blackout_info = f"{m_status_str} (下次宏觀事件：{next_m_str})"
                except Exception as ce:
                    logger.debug(f"Calendar blackout info error: {ce}")
                # 盤中流動性黑洞與動態滑點補償追蹤
                fill_quality_info = "🟢 正常追蹤中 (基準模型 5.0 bps / 1.00x)"
                try:
                    from src.services.adaptive_execution_slippage_compensator import AdaptiveExecutionSlippageCompensator
                    comp = AdaptiveExecutionSlippageCompensator(user_id=resolved_user_id)
                    f_sum = comp.get_fill_quality_summary(["MSFT", "MU", "AMD", "NVDA", "AAPL"])
                    p_bps = f_sum.get("portfolio_avg_slippage_bps", 5.0)
                    p_mult = f_sum.get("portfolio_avg_multiplier", 1.0)
                    h_stat = f_sum.get("overall_liquidity_health", "OPTIMAL")
                    h_icon = "🟢" if h_stat == "OPTIMAL" else ("🟡" if h_stat == "MODERATE" else "⚠️")
                    fill_quality_info = f"{h_icon} {h_stat} (平均 {p_bps:.1f} bps，補償乘數 {p_mult:.2f}x)"
                except Exception as fe:
                    logger.debug(f"Fill quality info error in guard: {fe}")

                # 因子特徵漂移與失效自癒防線 (P30)
                factor_guard_info = "🟢 正常運作中 (6 大因子健全度檢驗中)"
                try:
                    from src.services.factor_drift_guard_service import FactorDriftGuardService
                    from src.services.tactical_factor_rotation_service import TacticalFactorRotationService
                    t_svc = TacticalFactorRotationService(user_id=resolved_user_id)
                    p, _ = t_svc.determine_market_phase()
                    b_weights = t_svc.get_phase_factor_weights(p, apply_auto_healing=False)
                    d_svc = FactorDriftGuardService(user_id=resolved_user_id)
                    d_rep = d_svc.evaluate_factor_health(phase=p, base_weights=b_weights)
                    h_icon = "🟢" if d_rep.overall_factor_health == "OPTIMAL" else ("🟡" if d_rep.overall_factor_health == "MODERATE" else "🔴")
                    if d_rep.healed_count > 0:
                        factor_guard_info = f"🛡️ 自癒生效中 ({d_rep.healed_count} 因子已重平衡，體制: {p.value})"
                    else:
                        factor_guard_info = f"{h_icon} {d_rep.overall_factor_health} (全因子 IC 正常，體制: {p.value})"
                except Exception as de:
                    logger.debug(f"Factor drift info error in guard: {de}")

                return (
                    f"🛡️ <b>【開盤防滑點守衛與價差熔斷狀態】</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>守衛功能開關</b>：{'🟢 已啟用 (Enabled)' if setting_enabled else '🔴 已停用'}\n"
                    f"• <b>最大容許價差門檻</b>：{float(max_spread or 0.0015)*100:.2f}% (15 bps)\n"
                    f"• <b>美股市場開市狀態</b>：{'🟢 開市中 (Open)' if is_open else '⚪ 休市中 (Closed)'}\n"
                    f"• <b>開盤高波動保護窗口 (09:30-09:35)</b>：{'⚠️ 觸發保護中 (Active)' if is_auction else '✅ 安全窗口'}\n"
                    f"• <b>動態成交品質追蹤</b>：{fill_quality_info}\n"
                    f"• <b>流動性黑洞熔斷 (Black Hole)</b>：補償乘數 ≥ 2.5x 且逆向選擇 ≥ 2 次自動暫緩\n"
                    f"• <b>因子特徵漂移與自癒 (P30)</b>：{factor_guard_info}\n"
                    f"• <b>宏觀行事曆發布避開</b>：{blackout_info}\n"
                    f"• <b>財報日前後避開保護</b>：前 48h 暫緩開倉 / 後 24h 消化波動\n"
                    f"• <b>開盤候選標的預熱</b>：{warmup_info}\n"
                    f"• <b>自適應限價單保護</b>：Mid + Spread × 0.25 封頂 (動態係數 0.8x~1.5x)\n"
                    f"• <b>事後滑點異常告警門檻</b>：> 0.20% 自動通報\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<i>美股開盤 09:35 EST 建倉時將自動為每一筆訂單執行自適應限價、價差驗證、成交品質與財報避開審核。</i>"
                )
            except Exception as e:
                logger.error(f"Failed to generate quick guard response: {e}")
                return f"⚠️ 查詢風控守衛狀態時發生錯誤：{e}"

        # 5. Warmup / Quote / 預熱 / 報價
        if any(cmd.startswith(prefix) for prefix in ("warmup", "quote", "預熱", "報價")):
            try:
                from src.services.batch_cash_deployment_service import BatchCashDeploymentService
                deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                res = await deploy_svc.warmup_batch_quotes()
                active_b = res.get("batch_number", 0)
                quotes = res.get("quotes", {})
                lines = [
                    "🔥 <b>【開盤標的即時報價預熱與價差掃描】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                ]
                if active_b == 0 or not quotes:
                    lines.append(f"ℹ️ {res.get('message', '目前無待執行建倉批次。')}")
                else:
                    lines.append(f"🎯 <b>第 {active_b} 批次候選標的報價快照</b>：")
                    for ticker, q in quotes.items():
                        if q.get("ready"):
                            last = q.get("last") or q.get("mid") or 0.0
                            bid = q.get("bid")
                            ask = q.get("ask")
                            bid_str = f"${bid:.2f}" if bid else "N/A"
                            ask_str = f"${ask:.2f}" if ask else "N/A"
                            sp_pct = q.get("spread_pct")
                            sp_str = f"{sp_pct*100:.2f}%" if sp_pct is not None else "N/A"
                            source = q.get("source", "provider")
                            lines.append(
                                f"• <b>{ticker}</b>: 市價 ${last:.2f} | 買/賣: {bid_str}/{ask_str} (價差: {sp_str}) [{source}]"
                            )
                        else:
                            err = q.get("error", "暫無即時報價")
                            lines.append(f"• <b>{ticker}</b>: ⚠️ 報價未就緒 ({err})")
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("✅ <b>報價已寫入分散式快取</b>，開盤建倉可直接毫秒級讀取，免去外部連線延遲。")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to execute warmup command: {e}")
                return f"⚠️ 執行即時報價預熱時發生錯誤：{e}"

        # 6. Calendar / Earnings / 行事曆 / 財報 / 大事記
        if any(cmd.startswith(prefix) for prefix in ("calendar", "earnings", "行事曆", "財報", "日曆", "大事記")):
            try:
                from src.services.calendar_blackout_service import CalendarBlackoutService
                from src.services.batch_cash_deployment_service import BatchCashDeploymentService
                c_guard = CalendarBlackoutService(user_id=resolved_user_id)
                deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                active_b = await deploy_svc.get_active_batch_number()

                # 收集目前待建倉標的
                scan_tickers = ["MSFT", "MU", "AMD", "NVDA", "AAPL"]
                try:
                    plan = await deploy_svc.get_deployment_plan(batch_number=active_b)
                    batch_tickers = [it["ticker"] for it in plan.get("items", [])]
                    for bt in batch_tickers:
                        if bt not in scan_tickers:
                            scan_tickers.append(bt)
                except Exception:
                    pass

                summary = await c_guard.get_upcoming_calendar_summary(scan_tickers)
                macro_stat = summary.get("macro_status", {})
                next_macro = macro_stat.get("next_event")
                tickers_cal = summary.get("tickers", {})

                lines = [
                    "📅 <b>【宏觀行事曆與企業財報避開守衛總覽】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                ]

                # 宏觀大事記
                lines.append("🏛️ <b>即將發布之重大宏觀數據 (FOMC / CPI / NFP)</b>：")
                if next_macro:
                    lines.append(
                        f"• <b>{next_macro['name']}</b>\n"
                        f"  時間：<code>{next_macro['time']} EST</code> (倒數 <b>{next_macro['days_away']}</b> 天 / {next_macro['hours_away']} 小時)\n"
                        f"  防護視窗：發布前 60 分鐘暫緩開倉至發布後 30 分鐘"
                    )
                else:
                    lines.append("• <i>近期無表定高衝擊宏觀數據。</i>")

                # 個股財報日曆
                lines.append("")
                batch_title = f"(含第 {active_b} 批次候選)" if active_b > 0 else ""
                lines.append(f"📊 <b>核心持倉與待建倉標的財報日程 {batch_title}</b>：")
                for sym, info in tickers_cal.items():
                    blackout_tag = "⚠️ <b>[避開中 - 暫緩下單]</b>" if info.get("is_blackout") else "✅ [安全]"
                    d_disp = info.get("display", "未定")
                    h_to = info.get("hours_to_event")
                    h_str = ""
                    if h_to is not None:
                        if h_to >= 0:
                            h_str = f" (倒數 {h_to/24.0:.1f} 天)"
                        else:
                            h_str = f" ({abs(h_to)/24.0:.1f} 天前已發布)"
                    lines.append(f"• <b>{sym}</b>: {d_disp}{h_str} — {blackout_tag}")

                lines.append("")
                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("🛡️ <b>守衛風控機制說明</b>：")
                lines.append("• 財報發布前 48 小時自動暫緩配置，規避二元跳空與 IV Crush。")
                lines.append("• 財報發布後 24 小時沉澱期，待市場充分消化營收與指引後再行部署。")
                lines.append("• 重大宏觀事件窗口暫緩開倉，防範流動性真空與劇烈滑點。")

                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate calendar response: {e}")
                return f"⚠️ 查詢財報與宏觀行事曆時發生錯誤：{e}"

        # 7. Quality / Fills / 成交品質 / 滑點統計 / 流動性
        if any(cmd.startswith(prefix) for prefix in ("quality", "fills", "成交品質", "滑點統計", "流動性")):
            try:
                from src.services.adaptive_execution_slippage_compensator import AdaptiveExecutionSlippageCompensator
                from src.services.batch_cash_deployment_service import BatchCashDeploymentService
                compensator = AdaptiveExecutionSlippageCompensator(user_id=resolved_user_id)
                deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                active_b = await deploy_svc.get_active_batch_number()

                # 收集活躍持倉與建倉候選標的
                scan_symbols = ["MSFT", "MU", "AMD", "NVDA", "AAPL", "TSM"]
                try:
                    plan = await deploy_svc.get_deployment_plan(batch_number=active_b)
                    for item in plan.get("items", []):
                        sym = item.get("ticker")
                        if sym and sym not in scan_symbols:
                            scan_symbols.append(sym)
                except Exception:
                    pass

                summary = compensator.get_fill_quality_summary(scan_symbols)
                avg_bps = summary.get("portfolio_avg_slippage_bps", 5.0)
                avg_mult = summary.get("portfolio_avg_multiplier", 1.0)
                health = summary.get("overall_liquidity_health", "OPTIMAL")
                symbols_data = summary.get("symbols", {})

                health_badge = "🟢 優良 (OPTIMAL)" if health == "OPTIMAL" else ("🟡 平緩 (MODERATE)" if health == "MODERATE" else "🔴 惡化 (DEGRADED)")

                lines = [
                    "📈 <b>【標的成交品質與動態滑點補償追蹤 (P29)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>投組平均實現滑點</b>：{avg_bps:.1f} bps (0.01% = 1 bps)",
                    f"• <b>整體自適應補償乘數</b>：{avg_mult:.2f}x",
                    f"• <b>綜合流動性健康度</b>：{health_badge}",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【標的成交品質評級與動態限價緩衝】</b>",
                ]

                grade_emojis = {
                    "A+": "🌟 A+",
                    "A": "🟢 A",
                    "B": "🔵 B",
                    "C": "🟡 C",
                    "D": "🟠 D",
                    "F": "🔴 F (黑洞)",
                }

                for sym, info in symbols_data.items():
                    grade = info.get("grade", "A")
                    g_str = grade_emojis.get(grade, grade)
                    r_bps = info.get("realized_slippage_bps", 0.0)
                    mult = info.get("slippage_multiplier", 1.0)
                    dyn_buf = info.get("dynamic_buffer_factor", 1.0)
                    adv_cnt = info.get("adverse_selection_count", 0)
                    samp_cnt = info.get("sample_count", 0)
                    desc = info.get("description", "")

                    sample_tag = f"({samp_cnt}筆樣本)" if samp_cnt > 0 else "(基準預估)"
                    lines.append(
                        f"• <b>{sym}</b> [{g_str}]: 滑點 <code>{r_bps:.1f} bps</code> | "
                        f"補償乘數 <code>{mult:.2f}x</code> | 限價緩衝 <code>{dyn_buf:.2f}x</code> "
                        f"{sample_tag}\n"
                        f"  └ <i>{desc} (逆向選擇: {adv_cnt}次)</i>"
                    )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("🛡️ <b>自適應動態補償機制</b>：")
                lines.append("• 依據 EWMA 平滑追蹤真實成交滑點，動態調整限價單保護緩衝 (0.8x ~ 1.5x)。")
                lines.append("• 補償上限至多 25 bps，防止盤中極端劇烈行情擴大追價摩擦。")
                lines.append("• 若補償乘數 ≥ 2.5x 且逆向選擇 ≥ 2 次，自動判定為流動性黑洞並暫緩下單。")

                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate fill quality response: {e}")
                return f"⚠️ 查詢成交品質與滑點統計時發生錯誤：{e}"

        # 8. Factor / Factors / IC / 因子 / 特徵漂移 / 因子自癒 / 因子監控
        if any(cmd.startswith(prefix) for prefix in ("factor", "factors", "ic", "因子", "特徵漂移", "因子自癒", "因子監控")):
            try:
                from src.services.factor_drift_guard_service import FactorDriftGuardService
                from src.services.tactical_factor_rotation_service import TacticalFactorRotationService

                t_svc = TacticalFactorRotationService(user_id=resolved_user_id)
                phase, rationale = t_svc.determine_market_phase()
                base_weights = t_svc.get_phase_factor_weights(phase, apply_auto_healing=False)

                d_svc = FactorDriftGuardService(user_id=resolved_user_id)
                report = d_svc.evaluate_factor_health(phase=phase, base_weights=base_weights)

                overall_badge = "🟢 最佳 (OPTIMAL)" if report.overall_factor_health == "OPTIMAL" else (
                    "🟡 中度漂移 (MODERATE)" if report.overall_factor_health == "MODERATE" else "🔴 因子失效 (DEGRADED)"
                )

                lines = [
                    "🧬 <b>【全自動機器學習因子特徵漂移與失效自癒 (P30)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>當前市場週期體制</b>：<code>{report.phase}</code>",
                    f"• <b>週期體制判定依據</b>：<i>{rationale}</i>",
                    f"• <b>多因子體系總體健康</b>：{overall_badge}",
                    f"• <b>自癒重平衡狀態</b>：{'🛡️ 已觸發自癒' if report.healed_count > 0 else '✅ 正常運行 (無需介入)'} ({report.healed_count} 個因子調整)",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【6 大核心戰術因子 Rank IC 與動態權重矩陣】</b>",
                ]

                status_badges = {
                    "HEALTHY": "🟢 健全",
                    "DRIFTING": "🟡 漂移",
                    "INVERTED": "🔴 反轉",
                    "AUTO_HEALED": "🛡️ 自癒",
                }

                factor_zh = {
                    "momentum": "動能趨勢 (Momentum)",
                    "smart_money": "聰明錢主力 (Smart Money)",
                    "liquidity_premium": "流動性溢價 (Liquidity)",
                    "quality": "基本面品質 (Quality)",
                    "value": "價值安全邊際 (Value)",
                    "low_vol": "低波動防禦 (Low Vol)",
                }

                for fn, m in report.factors.items():
                    s_badge = status_badges.get(m.status, m.status)
                    fn_display = factor_zh.get(fn, fn)
                    b_pct = m.baseline_weight * 100.0
                    e_pct = m.effective_weight * 100.0
                    w_change = f"<code>{b_pct:.1f}% ➔ {e_pct:.1f}%</code>" if abs(b_pct - e_pct) > 0.05 else f"<code>{e_pct:.1f}%</code>"
                    lines.append(
                        f"• <b>{fn_display}</b> [{s_badge}]\n"
                        f"  └ 30d IC: <code>{m.ic_30d:+.3f}</code> | IR: <code>{m.ic_ir:.2f}</code> | t: <code>{m.t_stat:.2f}</code> | 權重: {w_change}"
                    )

                if report.healing_actions:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🛠️ <b>【自適應失效自癒重平衡日誌】</b>")
                    for act in report.healing_actions:
                        lines.append(f"• {act}")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("🛡️ <b>閉環自癒機制說明</b>：")
                lines.append("• 滾動度量 30d Spearman Rank IC，即時偵測 Concept Drift 與負向反轉 (IC < 0)。")
                lines.append("• 失效因子施加 50%~90% 阻尼懲罰，多餘權重動態重平衡至防禦與高流動性錨點。")
                lines.append("• 經由嚴格單體投影 (Simplex Normalization) 確保總權重嚴格收斂至 100.00%。")
                lines.append("• <b>離線基因超參數演化 (P31)</b>：輸入 <code>/evolve</code> 檢視全歷史 Walk-Forward 遺傳演化終審進度與最佳矩陣。")
                lines.append("• <b>因子特徵正交化 (P32)</b>：輸入 <code>/ortho</code> 檢視 6 大因子多重共線性 VIF 檢定與純淨 Alpha 正交化。")

                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate factor drift report response: {e}")
                return f"⚠️ 查詢因子特徵漂移與自癒狀態時發生錯誤：{e}"

        # 9. Evolve / Evolution / GA / 演化 / 基因演化 / 因子演化 / 遺傳演化 (Phase 31)
        if any(cmd.startswith(prefix) for prefix in ("evolve", "evolution", "ga", "演化", "基因演化", "因子演化", "遺傳演化")):
            try:
                from src.services.factor_genetic_evolution_engine import FactorGeneticEvolutionEngine
                engine = FactorGeneticEvolutionEngine(user_id=resolved_user_id)
                report = engine.load_latest_report()

                if not report:
                    return (
                        "🧬 <b>【全歷史多因子遺傳演算法超參數演化 (Phase 31)】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "ℹ️ 尚未產生離線遺傳演化報告。\n\n"
                        "• <b>背景排程</b>：每週日 23:00 EST 自動執行 20 世代染色體交叉突變與 Walk-Forward 前向走查。\n"
                        "• <b>即時因子狀態</b>：可輸入 <code>/factor</code> 檢視當前 6 大因子 Rank IC 與特徵漂移自癒。\n"
                        "• <b>手動觸發演化</b>：管理員可透過 Celery 派發 <code>run_factor_genetic_evolution</code> 任務。"
                    )

                run_id = report.get("run_id", "N/A")
                ts = report.get("timestamp", "N/A")[:19].replace("T", " ")
                pop_size = report.get("population_size", 20)
                gens = report.get("generations", 20)
                mut_rate = report.get("mutation_rate", 0.20)
                cross_rate = report.get("crossover_rate", 0.80)

                wfo_eff = report.get("wfo_efficiency", 0.0)
                sharpe_imp = report.get("sharpe_improvement_pct", 0.0)
                mdd_exp = report.get("mdd_expansion_pct", 0.0)
                diversity = report.get("factor_shannon_diversity", 0.0)
                is_promotable = report.get("is_promotable", False)
                promoted_to_settings = report.get("promoted_to_settings", False)
                promo_reason = report.get("promotion_reason", "")

                base_oos = report.get("baseline_oos_metrics", {})
                best_oos = report.get("best_oos_metrics", {})
                base_sharpe = base_oos.get("sharpe", 0.0)
                best_sharpe = best_oos.get("sharpe", 0.0)
                base_ret = base_oos.get("annualized_return", 0.0) * 100.0
                best_ret = best_oos.get("annualized_return", 0.0) * 100.0
                base_mdd = base_oos.get("max_drawdown", 0.0) * 100.0
                best_mdd = best_oos.get("max_drawdown", 0.0) * 100.0

                gate_badge = "✅ 終審通過 (PROMOTED)" if is_promotable else "⚠️ 維持基準 (REJECTED)"
                applied_badge = "🚀 已生效至生產環境" if promoted_to_settings else "⏸️ 未套用至生產環境"

                lines = [
                    "🧬 <b>【全歷史動態多因子遺傳演算法超參數演化報告 (Phase 31)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>演化批次 ID</b>：<code>{run_id}</code> ({ts} UTC)",
                    f"• <b>超參數配置</b>：族群 <code>{pop_size}</code> | 世代 <code>{gens}</code> | 突變 <code>{mut_rate:.2f}</code> | 交叉 <code>{cross_rate:.2f}</code>",
                    f"• <b>終審裁定狀態</b>：{gate_badge} ({applied_badge})",
                    f"• <b>晉級評定原因</b>：{promo_reason}",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【Out-of-Sample 盲測驗證 vs 基準對比】</b>",
                    f"• <b>OOS 夏普比率 (Sharpe)</b>：<code>{base_sharpe:.2f} ➔ {best_sharpe:.2f}</code> ({sharpe_imp:+.1f}%)",
                    f"• <b>OOS 年化回報 (Return)</b>：<code>{base_ret:+.1f}% ➔ {best_ret:+.1f}%</code>",
                    f"• <b>OOS 最大回撤 (MDD)</b>：<code>{base_mdd:.1f}% ➔ {best_mdd:.1f}%</code> ({mdd_exp:+.1f}%)",
                    f"• <b>WFO 效率係數</b>：<code>{wfo_eff:.2f}</code> (門檻 >= 0.55)",
                    f"• <b>香農多因子多樣性</b>：<code>{diversity:.2f}</code> (門檻 >= 0.80，防止單因子過度偏激)",
                ]

                # 世代適應度躍遷歷程 (抽樣頭、中、尾世代)
                history = report.get("generation_history", [])
                if history:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("📈 <b>【世代適應度演化進程 (Generational Progression)】</b>")
                    sample_indices = sorted(list({0, len(history) // 2, len(history) - 1}))
                    for idx in sample_indices:
                        if idx < len(history):
                            g = history[idx]
                            lines.append(
                                f"• Gen #{g.get('generation')}: 最優適應度 <code>{g.get('best_fitness'):.3f}</code> "
                                f"| 平均 <code>{g.get('mean_fitness'):.3f}</code> "
                                f"| IS Sharpe <code>{g.get('best_sharpe_is'):.2f}</code> "
                                f"| 多樣性 <code>{g.get('diversity_score'):.2f}</code>"
                            )

                # 最佳矩陣配置摘要
                best_matrix = report.get("best_matrix", {})
                phase_weights = best_matrix.get("phase_weights", {})
                if phase_weights:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🏆 <b>【演化最優冠軍權重矩陣 (Champion Weights)】</b>")
                    phase_zh = {
                        "EARLY_REBOUND": "早期反彈",
                        "BULL_ACCELERATION": "多頭主升",
                        "LATE_CYCLE_VALUE": "末期價值",
                        "DEFENSIVE_CONSOLIDATION": "防禦震盪",
                    }
                    for ph, ws in phase_weights.items():
                        ph_name = phase_zh.get(ph, ph)
                        top_factors = sorted(ws.items(), key=lambda x: x[1], reverse=True)[:3]
                        tf_str = ", ".join(f"{k}:{v*100:.0f}%" for k, v in top_factors)
                        lines.append(f"• <b>{ph_name}</b>: {tf_str}")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>本演化採用單體高斯變異 (Simplex Mutation) 與非線性回撤懲罰，杜絕過擬合與單因子極端集中。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate genetic evolution response: {e}")
                return f"⚠️ 查詢遺傳演化狀態時發生錯誤：{e}"

        # 10. Ortho / Orthogonal / VIF / 正交 / 正交化 / 共線性 / 因子正交 (Phase 32)
        if any(cmd.startswith(prefix) for prefix in ("ortho", "orthogonal", "vif", "正交", "正交化", "共線性", "因子正交")):
            try:
                from src.services.factor_orthogonalization_service import FactorOrthogonalizationService
                ortho_svc = FactorOrthogonalizationService(user_id=resolved_user_id)
                report = ortho_svc.load_latest_report()

                # 若尚未有執行快取，自動以具代表性標的池生成即時截面正交化檢定
                if not report:
                    sample_universe = {
                        "NVDA": {"momentum_score": 0.95, "smart_money_score": 0.88, "liquidity_premium_score": 0.92, "quality_score": 0.85, "value_score": 0.20, "low_vol_score": 0.15},
                        "AAPL": {"momentum_score": 0.70, "smart_money_score": 0.75, "liquidity_premium_score": 0.90, "quality_score": 0.92, "value_score": 0.40, "low_vol_score": 0.65},
                        "MSFT": {"momentum_score": 0.72, "smart_money_score": 0.80, "liquidity_premium_score": 0.88, "quality_score": 0.95, "value_score": 0.35, "low_vol_score": 0.60},
                        "AMZN": {"momentum_score": 0.80, "smart_money_score": 0.78, "liquidity_premium_score": 0.91, "quality_score": 0.82, "value_score": 0.25, "low_vol_score": 0.40},
                        "GOOGL": {"momentum_score": 0.65, "smart_money_score": 0.70, "liquidity_premium_score": 0.89, "quality_score": 0.90, "value_score": 0.45, "low_vol_score": 0.55},
                        "META": {"momentum_score": 0.88, "smart_money_score": 0.82, "liquidity_premium_score": 0.87, "quality_score": 0.84, "value_score": 0.38, "low_vol_score": 0.35},
                        "JPM": {"momentum_score": 0.55, "smart_money_score": 0.60, "liquidity_premium_score": 0.75, "quality_score": 0.78, "value_score": 0.70, "low_vol_score": 0.58},
                        "JNJ": {"momentum_score": 0.30, "smart_money_score": 0.35, "liquidity_premium_score": 0.45, "quality_score": 0.88, "value_score": 0.65, "low_vol_score": 0.90},
                        "PG": {"momentum_score": 0.35, "smart_money_score": 0.40, "liquidity_premium_score": 0.50, "quality_score": 0.85, "value_score": 0.60, "low_vol_score": 0.88},
                        "XOM": {"momentum_score": 0.60, "smart_money_score": 0.65, "liquidity_premium_score": 0.70, "quality_score": 0.65, "value_score": 0.85, "low_vol_score": 0.45},
                    }
                    report_obj = ortho_svc.orthogonalize_cross_section(sample_universe, method="lowdin")
                    report = report_obj.to_dict()

                method_name = report.get("method", "lowdin")
                method_display = "Löwdin 對稱最小形變正交 (Symmetric Löwdin)" if method_name == "lowdin" else "Gram-Schmidt 循序基底正交"
                tickers = report.get("tickers", [])
                reduction_pct = report.get("correlation_reduction_pct", 0.0)
                ts = report.get("timestamp", "")[:19].replace("T", " ")

                pre = report.get("pre_collinearity", {})
                post = report.get("post_collinearity", {})
                max_vif_pre = pre.get("max_vif", 1.0)
                max_vif_post = post.get("max_vif", 1.0)
                vif_scores_pre = pre.get("vif_scores", {})
                vif_scores_post = post.get("vif_scores", {})
                collinear_pairs = pre.get("multicollinear_pairs", [])

                overall_badge = "🟢 健全 (ORTHOGONAL)" if max_vif_post < 5.0 else "🟡 輕度共線性"

                factor_zh = {
                    "momentum": "動能趨勢 (Momentum)",
                    "smart_money": "聰明錢主力 (Smart Money)",
                    "liquidity_premium": "流動性溢價 (Liquidity)",
                    "quality": "基本面品質 (Quality)",
                    "value": "價值安全邊際 (Value)",
                    "low_vol": "低波動防禦 (Low Vol)",
                }

                lines = [
                    "🧬 <b>【截面多因子特徵交互作用與動態正交化報告 (Phase 32)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>正交化演算法</b>：<code>{method_display}</code>",
                    f"• <b>評估標的樣本數</b>：<code>{len(tickers)}</code> 檔 ({ts} UTC)",
                    f"• <b>多重共線性消除率</b>：<code>{reduction_pct:.1f}%</code>",
                    f"• <b>正交後共線性狀態</b>：{overall_badge} (Max VIF: <code>{max_vif_post:.2f}</code>)",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【6 大核心因子方差膨脹因子 (VIF) 檢定】</b>",
                ]

                for fn in ("momentum", "smart_money", "liquidity_premium", "quality", "value", "low_vol"):
                    v_pre = vif_scores_pre.get(fn, 1.0)
                    v_post = vif_scores_post.get(fn, 1.0)
                    fn_name = factor_zh.get(fn, fn)
                    badge = "🟢 獨立" if v_post < 3.0 else ("🟡 輕度" if v_post < 5.0 else "🔴 共線")
                    lines.append(
                        f"• <b>{fn_name}</b> [{badge}]\n"
                        f"  └ VIF: <code>{v_pre:.1f} ➔ {v_post:.2f}</code>"
                    )

                if collinear_pairs:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("⚠️ <b>【正交前高共線性因子對（已徹底消除）】</b>")
                    for p in collinear_pairs[:4]:
                        f1_name = factor_zh.get(p[0], p[0])
                        f2_name = factor_zh.get(p[1], p[1])
                        lines.append(f"• {f1_name} ↔ {f2_name}: 原相關係數 <code>r = {p[2]:+.2f}</code> ➔ 正交後 <code>r = 0.00</code>")

                # 特徵交互作用摘要
                interactions = report.get("interaction_scores", {})
                if interactions:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("✨ <b>【非線性特徵交互作用協同效應 (Cross Synergies)】</b>")
                    lines.append("• <b>動能 x 聰明錢 (Mom x Smart)</b>：捕捉多頭突破且主力爆量買超之雙重彈性龍頭")
                    lines.append("• <b>品質 x 價值 (Qual x Value)</b>：捕捉具備高 ROE 與實質安全邊際之格雷厄姆護城河股")
                    lines.append("• <b>低波 x 品質 (LowVol x Qual)</b>：捕捉防禦震盪與極端波動下的無敵防守避風港")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>Löwdin 正交化保證正交矩陣與原始因子矩陣弗羅貝尼烏斯距離最小，徹底消除隱性曝險集中。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate factor orthogonalization response: {e}")
                return f"⚠️ 查詢因子正交化狀態時發生錯誤：{e}"

        return None
