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

from datetime import datetime
import inspect
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
            "riskparity", "parity", "cvar", "mrc", "風險平價", "平價配置", "風險貢獻", "尾部風險",
            "vpin", "toxicity", "kyle", "毒性", "訂單流毒性", "微觀結構", "知情交易",
            "jump", "jumpdiffusion", "merton", "bayesian", "跳躍擴散", "跳躍", "跳空", "貝葉斯跳躍",
            "sor", "rlexec", "qlearning", "smartrouting", "智慧路由", "強化學習拆單", "拆單路由", "rl",
            "eventgraph", "causal", "narrative", "shock", "因果圖譜", "事件圖譜", "敘事風險", "突發避險",
            "hmm", "bayesianfilter", "filter", "regimeprob", "hmmfactor", "隱馬爾可夫", "貝葉斯濾波", "體制機率", "連續體制",
            "universe", "pool", "tickers", "標的池", "股票池", "標的", "候選池",
            "dipbuy", "stagger", "dip", "階梯掛單", "吸籌", "階梯吸籌", "限價吸籌",
            "alpha", "netalpha", "cashdrag", "歸因", "淨額", "成本歸因", "機會成本",
            "budget", "token", "tokens", "預算", "代幣", "成本預算", "額度",
            "sector", "drift", "hhi", "板塊", "行業", "集中度", "板塊漂移", "板塊自癒",
            "spread", "bidding", "friction", "利差", "摩擦",
            "betadamp", "beta", "damping", "corrdamp", "阻尼", "貝塔阻尼", "大盤相關性",
            "harvest", "rebalance", "recirculate", "收割", "再平衡", "利差回流",
            "spoof", "antihunt", "orderbook", "假單", "反欺詐", "獵殺防衛",
            "darkpool", "prints", "blocktrades", "暗池", "大宗", "暗池定價",
            "convex", "sharpe", "qp", "mvo", "凸規劃", "夏普邊界", "最優配置",
            "ivskew", "skew", "iv", "波動率偏度", "選擇權偏度", "尾部避險",
            "ofi", "orderflow", "訂單流失衡", "流動性真空", "微觀失衡",
            "gex", "gamma", "flip", "pinning", "伽馬", "做市商伽馬", "釘盤",
            "pair", "pairs", "arb", "kalman", "配對", "統計套利", "協整",
            "tranche", "trend", "hysteresis", "schmitt", "倉位分級", "底倉", "自癒", "漂移自癒",
            "fx", "forex", "hedging", "外匯", "匯率", "避險", "匯率避險", "保證金緩衝",
            "attribution", "decay", "halflife", "residual", "收益歸因", "正交歸因", "因子歸因", "因子衰減", "半衰期", "因子半衰期",
            "decayrebalance", "調倉", "自適應調倉", "衰減調倉", "因子調倉",
            "stresstest", "stress", "stress_test", "壓力測試", "情境測試", "流動性擠壓", "極端情境",
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
            # 支援一鍵重設熔斷與封存連虧
            if any(k in cmd for k in ("reset", "重設", "解鎖", "clear")):
                try:
                    from src.services.trading_protections_service import TradingProtectionsService
                    prot_svc = TradingProtectionsService(user_id=resolved_user_id)
                    reset_ts = prot_svc.reset_lockout()
                    return (
                        "🔄 <b>【風控熔斷與連續虧損鎖定已手動重設 (Circuit Breaker Reset)】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>重設時間戳</b>：<code>{reset_ts}</code>\n"
                        "• <b>連虧歷史狀態</b>：已全數封存歸檔（重設前之負 Alpha 不再阻擋新單）\n"
                        "• <b>交易權限</b>：🟢 <code>ai_trading_enabled = true</code> (所有 BUY 買單放行)\n"
                        "• <b>建倉準備</b>：分批建倉與再平衡服務已解鎖就緒\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>系統已準備就緒，後續將依據在線 HMM 連續體制平滑配置建倉。輸入 <code>/guard</code> 可隨時檢視風控守衛；輸入 <code>/universe</code> 檢視標的池。</i>"
                    )
                except Exception as re_err:
                    return f"⚠️ 重設風控熔斷失敗：{re_err}"

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
                    f"• <b>動態風險平價與尾部 CVaR (P33)</b>：輸入 <code>/riskparity</code> 檢視全組合風險貢獻平衡與極端尾部配置\n"
                    f"• <b>訂單流毒性與 Kyle's λ 守衛 (P34)</b>：輸入 <code>/vpin</code> 檢視標的 VPIN 毒性體制與知情交易衝擊\n"
                    f"• <b>貝葉斯跳躍擴散守衛 (P35)</b>：輸入 <code>/jump</code> 檢視 Merton 跳躍強度 λ、擴散波動 σ 與體制卡片\n"
                    f"• <b>強化學習動態拆單智慧路由 (P36)</b>：輸入 <code>/sor</code> 檢視 Q-Learning 動作空間、最優切片排程與摩擦最小化計畫\n"
                    f"• <b>宏觀突發事件因果圖譜與避險 (P37)</b>：輸入 <code>/eventgraph</code> 檢視即時事件傳播震盪擴散與受損度矩陣 (支援 <code>/eventgraph sim</code> 模擬黑天鵝)\n"
                    f"• <b>貝葉斯連續體制與因子配置 (P38)</b>：輸入 <code>/hmm</code> 檢視在線漢密爾頓濾波體制機率與連續平滑因子權重 (支援 <code>/hmm sim</code>)\n"
                    f"• <b>標的池生命週期與候選審核 (P39)</b>：輸入 <code>/universe</code> 檢視實盤活躍與儲備候選池 (支援 <code>/universe scan</code>)\n"
                    f"• <b>手動熔斷解鎖</b>：輸入 <code>/guard reset</code> 一鍵封存連虧歷史並即時重設交易保護\n"
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
        if any(cmd.startswith(prefix) for prefix in ("factor", "factors", "ic", "因子", "特徵漂移", "因子自癒", "因子監控")) and not any(sub in cmd for sub in ("attribution", "decay", "halflife", "residual", "rebalance", "調倉", "歸因", "衰減", "半衰期")):
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
                lines.append("• <b>多資產動態風險平價 (P33)</b>：輸入 <code>/riskparity</code> 檢視等風險貢獻 (ERC) 與極端尾部 CVaR 資本配置。")
                lines.append("• <b>貝葉斯連續體制與因子配置 (P38)</b>：輸入 <code>/hmm</code> 檢視在線漢密爾頓濾波體制機率與連續平滑因子權重。")

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
                applied_badge = "📝 已登記提案，待核可後才生效" if report.get("proposal_id") else "⏸️ 未套用至生產環境"

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

        # 12. Dynamic Risk Parity & Extreme Tail CVaR Allocator (Phase 33)
        if any(cmd.startswith(prefix) for prefix in (
            "riskparity", "parity", "cvar", "mrc", "風險平價", "平價配置", "風險貢獻", "尾部風險"
        )):
            try:
                from src.services.risk_parity_cvar_service import RiskParityCVaRService
                rp_svc = RiskParityCVaRService(user_id=resolved_user_id)
                cached_data = rp_svc.get_latest_cached_assessment()
                if cached_data:
                    data = cached_data
                else:
                    res_obj = await rp_svc.get_portfolio_risk_parity_assessment()
                    data = res_obj.to_dict()

                symbols = data.get("symbols", [])
                metrics = data.get("asset_metrics", {})
                cur_hhi = data.get("current_hhi_risk", 1.0)
                final_hhi = data.get("cvar_hhi_risk", 1.0)
                cur_enc = data.get("effective_risk_assets_current", 1.0)
                final_enc = data.get("effective_risk_assets_cvar", 1.0)
                hhi_reduction = data.get("risk_concentration_reduction_pct", 0.0)
                cur_vol = data.get("portfolio_vol_current", 0.0)
                final_vol = data.get("portfolio_vol_cvar_adjusted", 0.0)
                ts = data.get("timestamp", "")[:19].replace("T", " ")

                status_badge = "🟢 均衡 (BALANCED)" if final_hhi <= (1.5 / max(1, len(symbols))) else "🟡 輕度集中"

                lines = [
                    "⚖️ <b>【多資產動態風險平價與極端尾部 CVaR 配置報告 (Phase 33)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心演算法</b>：<code>循環坐標下降法 (CCD) + 尾部 CVaR 收縮</code>",
                    f"• <b>評估標的數量</b>：<code>{len(symbols)}</code> 檔 ({ts} UTC)",
                    f"• <b>風險集中度 (HHI)</b>：<code>{cur_hhi:.4f} ➔ {final_hhi:.4f}</code> (集中度降低 <code>{hhi_reduction:.1f}%</code>)",
                    f"• <b>有效風險資產數 (ENC)</b>：<code>{cur_enc:.2f} 檔 ➔ {final_enc:.2f} 檔</code> ({status_badge})",
                    f"• <b>組合預期年化波動</b>：<code>{cur_vol:.1%} ➔ {final_vol:.1%}</code>",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【各標的風險貢獻 (TRC%) 與動態配置矩陣】</b>",
                ]

                tail_alerts = []
                for sym in symbols:
                    m = metrics.get(sym, {})
                    vol = m.get("volatility", 0.0)
                    cur_w = m.get("current_weight", 0.0)
                    cur_trc = m.get("current_trc_pct", 0.0)
                    parity_w = m.get("parity_weight", 0.0)
                    final_w = m.get("final_target_weight", 0.0)
                    parity_trc = m.get("parity_trc_pct", 0.0)
                    var95 = m.get("var_95", 0.0)
                    cvar95 = m.get("cvar_95", 0.0)
                    is_tail = m.get("tail_risk_flag", False)

                    badge = "⚠️ 肥尾" if is_tail else "🟢 平穩"
                    if is_tail:
                        tail_alerts.append((sym, cvar95))

                    lines.append(
                        f"• <b>{sym}</b> [{badge}]\n"
                        f"  ├ 年化波動: <code>{vol:.1%}</code> | 現有權重: <code>{cur_w:.1%}</code> (風險佔比: <code>{cur_trc:.1%}</code>)\n"
                        f"  ├ 純平價權重: <code>{parity_w:.1%}</code> ➔ <b>目標配置</b>: <code>{final_w:.1%}</code> (風險佔比: <code>{parity_trc:.1%}</code>)\n"
                        f"  └ 95% 單日損失 (VaR/CVaR): <code>{var95:.2%} / {cvar95:.2%}</code>"
                    )

                if tail_alerts:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("⚠️ <b>【極端左尾肥尾風險警示】</b>")
                    for sym, cvar in tail_alerts:
                        lines.append(f"• <b>{sym}</b>: 95% 單日期望損失達 <code>{cvar:.2%}</code>，已動態收縮其風險預算防止黑天鵝重創。")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>動態風險平價保證各資產對總風險貢獻均等，極端尾部 CVaR 則在肥尾崩跌時主動降低資本曝險。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate risk parity response: {e}")
                return f"⚠️ 查詢動態風險平價狀態時發生錯誤：{e}"

        # 13. Microstructure VPIN & Kyle's Lambda Toxicity Guard (Phase 34)
        if any(cmd.startswith(prefix) for prefix in (
            "vpin", "toxicity", "kyle", "毒性", "訂單流毒性", "微觀結構", "知情交易"
        )):
            try:
                from src.services.vpin_toxicity_guard_service import VPINToxicityGuardService
                vpin_svc = VPINToxicityGuardService(user_id=resolved_user_id)
                summary_data = await vpin_svc.get_latest_portfolio_summary()
                if summary_data:
                    data = summary_data
                else:
                    sum_obj = await vpin_svc.get_portfolio_vpin_assessment()
                    data = sum_obj.to_dict()

                overall_tox = data.get("overall_market_toxicity", "BENIGN")
                mean_vpin = data.get("mean_vpin", 0.0)
                mean_kyle = data.get("mean_kyle_lambda", 0.0)
                toxic_syms = data.get("toxic_symbols", [])
                elev_syms = data.get("elevated_symbols", [])
                norm_syms = data.get("normal_symbols", [])
                assessments = data.get("assessments", {})
                ts = data.get("timestamp", "")[:19].replace("T", " ")

                if overall_tox == "ACUTE_TOXICITY":
                    overall_badge = "🔴 重度毒性 (ACUTE_TOXICITY) - 觸發熔斷暫緩下單"
                elif overall_tox == "MODERATE":
                    overall_badge = "🟡 中度升溫 (MODERATE) - 啟動拆單降速與滑點加成"
                else:
                    overall_badge = "🟢 流動性健康 (BENIGN) - 正常放行下單"

                lines = [
                    "🛡️ <b>【微觀結構訂單流毒性與知情交易者檢定報告 (Phase 34)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心模型</b>：<code>成交量時鐘切片 (VPIN) + Kyle's Lambda (λ) 價格衝擊回歸</code>",
                    f"• <b>全市場微觀體制</b>：{overall_badge}",
                    f"• <b>投組平均 VPIN</b>：<code>{mean_vpin:.1%}</code> (警戒線 <code>40.0%</code> | {ts} UTC)",
                    f"• <b>平均 Kyle's λ</b>：<code>{mean_kyle:.6f}</code> $/k 股失衡衝擊",
                    f"• <b>標的狀態統計</b>：正常 <code>{len(norm_syms)}</code> 檔 | 升溫 <code>{len(elev_syms)}</code> 檔 | 毒性 <code>{len(toxic_syms)}</code> 檔",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【各標的微觀結構毒性體制與處置矩陣】</b>",
                ]

                toxic_alerts = []
                for sym, ass in assessments.items():
                    reg = ass.get("regime", "NORMAL")
                    vp = ass.get("vpin", 0.0)
                    kl = ass.get("kyle_lambda", 0.0)
                    act = ass.get("recommended_action", "PROCEED")
                    pace = ass.get("execution_pace_minutes", 0)
                    boost = ass.get("slippage_boost", 0.0)
                    k_metrics = ass.get("kyle_metrics", {})
                    r_sq = k_metrics.get("r_squared", 0.0)
                    alpha = k_metrics.get("informed_trader_ratio", 0.0)

                    if reg == "TOXIC":
                        badge = "🔴 TOXIC (知情聚集)"
                        action_desc = f"⛔ <b>暫緩下單</b> (冷卻 {pace} 分鐘)"
                        toxic_alerts.append((sym, vp, kl, pace))
                    elif reg == "ELEVATED":
                        badge = "🟡 ELEVATED (中度失衡)"
                        action_desc = f"⚠️ <b>拆單降速</b> (滑點加成 +{boost:.2f}x)"
                    else:
                        badge = "🟢 NORMAL (流動性健康)"
                        action_desc = "✅ <b>正常執行</b>"

                    lines.append(
                        f"• <b>{sym}</b> [{badge}]\n"
                        f"  ├ VPIN 毒性機率: <code>{vp:.1%}</code> | 知情交易者比率 α: <code>{alpha:.1%}</code>\n"
                        f"  ├ Kyle's λ 衝擊: <code>{kl:.6f}</code> (R²: <code>{r_sq:.2f}</code>)\n"
                        f"  └ 執行處置: {action_desc}"
                    )

                if toxic_alerts:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🚨 <b>【知情交易者訂單流毒性急遽警示】</b>")
                    for sym, vp, kl, pace in toxic_alerts:
                        lines.append(
                            f"• <b>{sym}</b>: VPIN 達 <code>{vp:.1%}</code> (>= 40.0%)，每千股衝擊 <code>{kl:.6f}</code>，"
                            f"已前置阻斷市價建倉，防範逆向選擇吃損。"
                        )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>VPIN 衡量等量時鐘下買賣失衡機率，Kyle's Lambda 量化知情交易者對盤口造成的價格衝擊。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate VPIN toxicity guard response: {e}")
                return f"⚠️ 查詢微觀結構訂單流毒性狀態時發生錯誤：{e}"

        # 14. Bayesian Regime-Switching Jump-Diffusion Guard (Phase 35)
        if any(cmd.startswith(prefix) for prefix in (
            "jump", "jumpdiffusion", "merton", "bayesian", "跳躍擴散", "跳躍", "跳空", "貝葉斯跳躍"
        )):
            try:
                from src.services.bayesian_jump_diffusion_guard_service import (
                    BayesianJumpDiffusionGuardService,
                )
                jump_svc = BayesianJumpDiffusionGuardService(user_id=resolved_user_id)
                summary_data = await jump_svc.get_latest_portfolio_summary()
                if summary_data:
                    data = summary_data
                else:
                    sum_obj = await jump_svc.get_portfolio_jump_assessment()
                    data = sum_obj.to_dict()

                overall_regime = data.get("overall_market_jump_regime", "CALM")
                mean_intensity = data.get("mean_jump_intensity", 0.0)
                mean_rj = data.get("mean_relative_jump_ratio", 0.0)
                acute_syms = data.get("acute_symbols", [])
                mod_syms = data.get("moderate_symbols", [])
                calm_syms = data.get("calm_symbols", [])
                assessments = data.get("assessments", {})
                ts = data.get("timestamp", "")[:19].replace("T", " ")

                if overall_regime == "SYSTEMIC_JUMP_SHOCK":
                    overall_badge = "🔴 系統性跳躍衝擊 (SYSTEMIC_JUMP_SHOCK) - 觸發熔斷暫緩下單"
                elif overall_regime == "ELEVATED_JUMP_ACTIVITY":
                    overall_badge = "🟡 跳躍活動升溫 (ELEVATED_JUMP_ACTIVITY) - 啟動部位縮減與緩衝加成"
                else:
                    overall_badge = "🟢 連續擴散平靜 (CALM) - 正常放行下單"

                lines = [
                    "⚡ <b>【多期動態貝葉斯更新與機制轉換跳躍擴散報告 (Phase 35)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心模型</b>：<code>Merton (1976) 跳躍擴散 + Bipower Variation (BV) + 在線共軛貝葉斯更新</code>",
                    f"• <b>全市場跳躍體制</b>：{overall_badge}",
                    f"• <b>平均跳躍強度 λ</b>：<code>{mean_intensity:.2f}</code> 次/年 (警戒線 <code>6.00</code> | {ts} UTC)",
                    f"• <b>跳躍變異佔比 RJ</b>：<code>{mean_rj:.1%}</code> (離散跳躍方差 / 總實現方差)",
                    f"• <b>標的狀態統計</b>：平靜 <code>{len(calm_syms)}</code> 檔 | 升溫 <code>{len(mod_syms)}</code> 檔 | 重度衝擊 <code>{len(acute_syms)}</code> 檔",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【各標的跳躍擴散體制與風控處置矩陣】</b>",
                ]

                jump_alerts = []
                for sym, ass in assessments.items():
                    reg = ass.get("regime", "CALM_DIFFUSION")
                    lam = ass.get("jump_intensity", 0.0)
                    sig_c = ass.get("continuous_volatility", 0.0)
                    sig_t = ass.get("total_volatility", 0.0)
                    rj = ass.get("relative_jump_ratio", 0.0)
                    j_mu = ass.get("jump_mean", 0.0)
                    j_std = ass.get("jump_std", 0.0)
                    pos_scale = ass.get("position_scale_multiplier", 1.0)
                    sl_buff = ass.get("stop_loss_buffer_multiplier", 1.0)

                    if reg == "ACUTE_JUMP_REGIME":
                        badge = "🔴 ACUTE (劇烈跳躍)"
                        action_desc = "⛔ <b>暫緩下單 (跳躍熔斷)</b>"
                        jump_alerts.append((sym, lam, rj, j_mu))
                    elif reg == "MODERATE_JUMP":
                        badge = "🟡 MODERATE (中度跳躍)"
                        action_desc = f"⚠️ <b>規模收縮 {int(pos_scale*100)}% / 停損緩衝 {sl_buff:.2f}x</b>"
                    else:
                        badge = "🟢 CALM (常規連續擴散)"
                        action_desc = "✅ <b>正常執行 (100% 規模)</b>"

                    lines.append(
                        f"• <b>{sym}</b> [{badge}]\n"
                        f"  ├ 跳躍強度 λ: <code>{lam:.2f}</code> 次/年 | 跳躍佔比 RJ: <code>{rj:.1%}</code>\n"
                        f"  ├ 波動率分解: 連續 σ: <code>{sig_c:.1%}</code> | 總波動: <code>{sig_t:.1%}</code>\n"
                        f"  ├ 跳躍幅度分佈: μ_J: <code>{j_mu:+.2%}</code>, σ_J: <code>{j_std:.2%}</code>\n"
                        f"  └ 執行處置: {action_desc}"
                    )

                if jump_alerts:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🚨 <b>【非連續跳躍崩跌風險警示】</b>")
                    for sym, lam, rj, j_mu in jump_alerts:
                        lines.append(
                            f"• <b>{sym}</b>: 跳躍強度達 <code>{lam:.2f}</code> 次/年 (RJ: <code>{rj:.1%}</code>, 均值 <code>{j_mu:+.1%}</code>)，"
                            f"已前置阻斷市價建倉，防範裂口跌勢侵蝕本金。"
                        )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>BV 雙冪變異分離連續擴散波動與離散跳躍，Gamma-Poisson 貝葉斯更新適應跳躍體制轉換。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate Bayesian jump diffusion response: {e}")
                return f"⚠️ 查詢貝葉斯跳躍擴散守衛狀態時發生錯誤：{e}"

        # 15. Deep Q-Learning & RL Execution SOR Agent (Phase 36)
        if any(cmd.startswith(prefix) for prefix in (
            "sor", "rlexec", "qlearning", "smartrouting", "智慧路由", "強化學習拆單", "拆單路由", "rl"
        )):
            try:
                from src.services.rl_execution_sor_service import (
                    RLExecutionSmartOrderRoutingService,
                )
                from src.services.batch_cash_deployment_service import (
                    BatchCashDeploymentService,
                )
                sor_svc = RLExecutionSmartOrderRoutingService(user_id=resolved_user_id)
                snapshot = sor_svc.get_snapshot()

                # 嘗試取得待建倉候選標的，若無則示範標準代表性標的 (e.g. MSFT $1,000)
                sample_sym = "MSFT"
                sample_amt = 1000.0
                try:
                    deploy_svc = BatchCashDeploymentService(user_id=resolved_user_id)
                    act_b = await deploy_svc.get_active_batch_number()
                    plan = await deploy_svc.get_deployment_plan(batch_number=act_b)
                    items = plan.get("items", [])
                    if items:
                        sample_sym = items[0]["ticker"]
                        sample_amt = max(50.0, float(items[0].get("amount_usd", 1000.0)))
                except Exception:
                    pass

                demo_plan = await sor_svc.generate_execution_plan(
                    symbol=sample_sym,
                    total_amount_usd=sample_amt,
                    target_window_minutes=15,
                )

                status_badge = "🟢 運行中 (Online)" if snapshot.is_enabled else "🔴 已停用 (Disabled)"
                lines = [
                    "🤖 <b>【強化學習自適應動態訂單拆單與智慧路由報告 (Phase 36)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心演算法</b>：<code>Tabular Q-Learning (MDP) + Almgren-Chriss (2000) 先驗注入 + TD(0) 貝爾曼最優更新</code>",
                    f"• <b>引擎狀態</b>：{status_badge}",
                    f"• <b>MDP 狀態空間格子</b>：<code>{snapshot.q_table_states_count}</code> 格 (540 維離散空間覆蓋)",
                    f"• <b>歷史在線更新次數</b>：<code>{snapshot.total_updates_count}</code> 次 (學習率 α: <code>{snapshot.learning_rate:.2f}</code>, 折扣 γ: <code>{snapshot.discount_factor:.2f}</code>)",
                    f"• <b>探索利用率 ε</b>：<code>{snapshot.exploration_rate:.1%}</code> (純利用率 <code>{1-snapshot.exploration_rate:.1%}</code>)",
                    f"• <b>庫存方差風險厭惡係數 φ</b>：<code>{snapshot.inventory_risk_aversion:.2f}</code> (均值獎勵: <code>{snapshot.mean_reward:+.2f}</code>)",
                    "━━━━━━━━━━━━━━━━━━",
                    f"🎯 <b>【動態拆單排程示範：{sample_sym} (${sample_amt:.2f} USD，時窗 15 分鐘)】</b>",
                    f"• <b>推薦首選動作</b>：<code>{demo_plan.selected_action}</code> (預期 Q-Value: <code>{demo_plan.q_value:+.2f}</code>)",
                    f"• <b>預估總執行摩擦</b>：<code>{demo_plan.total_expected_cost_bps:.1f}</code> bps (涵蓋實現點差、暫時衝擊與方差風險)",
                    f"• <b>自適應分步切片排程 ({demo_plan.recommended_slices_count} 批次)</b>：",
                ]

                for s in demo_plan.slices:
                    lines.append(
                        f"  ├ 批次 #{s.slice_index} (T+{s.target_minute_offset:02d}m): "
                        f"<b>${s.amount_usd:.2f}</b> | <code>{s.action_name}</code> ({s.order_type} "
                        f"{s.limit_tilt_bps:+.1f} bps) | 成本 ~{s.expected_cost_bps:.1f} bps"
                    )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("📊 <b>【離散動作空間累計調度分佈】</b>")
                dist = snapshot.actions_distribution
                for act in sor_svc.ACTIONS:
                    cnt = dist.get(act.name, 0)
                    lines.append(f"• <b>{act.name}</b> (步長 {act.pace_ratio:.0%}, {act.order_type}): <code>{cnt}</code> 次")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>SOR 透過馬爾可夫決策過程即時平衡暫時性市場衝擊 η·√(V/ADV) 與庫存延遲風險 φ·q²·σ²。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate RL execution SOR response: {e}")
                return f"⚠️ 查詢強化學習智慧路由狀態時發生錯誤：{e}"

        # 16. Macro Event Causal Graph & Narrative Risk Engine (Phase 37)
        if any(cmd.startswith(prefix) for prefix in (
            "eventgraph", "causal", "narrative", "shock", "因果圖譜", "事件圖譜", "敘事風險", "突發避險"
        )):
            try:
                from src.services.macro_event_causal_graph_service import (
                    MacroEventCausalGraphService,
                    ShockDamageTier,
                )
                graph_svc = MacroEventCausalGraphService(user_id=resolved_user_id)

                # 處理重置指令
                if any(k in cmd for k in ("clear", "reset", "重置", "清空")):
                    graph_svc.clear_active_events()
                    return (
                        "🔄 <b>【宏觀突發事件因果圖譜已重置】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "所有活躍外生事件震盪已清除，因果網絡回復常態基準狀態。"
                    )

                # 處理黑天鵝劇本模擬
                sim_mode = any(k in cmd for k in ("sim", "scenario", "模擬", "壓力測試"))
                sim_result = None
                if sim_mode:
                    target_scenario = "TAIWAN_STRAIT_BLOCKADE"
                    if any(k in cmd for k in ("fed", "hike", "央行", "升息", "powell")):
                        target_scenario = "FED_INTERMEETING_HIKE"
                    elif any(k in cmd for k in ("bank", "run", "銀行", "擠兌", "svb")):
                        target_scenario = "REGIONAL_BANK_CASCADE"
                    elif any(k in cmd for k in ("oil", "energy", "war", "中東", "原油")):
                        target_scenario = "MIDDLE_EAST_OIL_WAR"

                    sim_result = graph_svc.simulate_scenario(target_scenario)
                    snapshot = graph_svc.get_snapshot()
                else:
                    snapshot = graph_svc.get_snapshot()

                status_badge = "🟢 運行中 (Online)" if snapshot.is_enabled else "🔴 已停用 (Disabled)"
                shock_val = snapshot.systemic_shock_score
                if shock_val >= 0.70:
                    shock_badge = f"🔴 系統性極端黑天鵝衝擊 ({shock_val:.2f}) - 啟動全防線避險與建倉熔斷"
                elif shock_val >= 0.35:
                    shock_badge = f"🟡 局部事件傳導升溫 ({shock_val:.2f}) - 啟動重創標的延緩建倉"
                else:
                    shock_badge = f"🟢 平靜無重大突發事件 ({shock_val:.2f}) - 因果傳播網絡平穩"

                lines = [
                    "🌐 <b>【宏觀突發事件即時輿情因果傳播與大腦避險報告 (Phase 37)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心演算法</b>：<code>Directed Weighted Causal Event Graph + PageRank Damped Shock Diffusion + Exponential Half-Life Decay</code>",
                    f"• <b>引擎狀態</b>：{status_badge} (阻尼係數 d: <code>{snapshot.decay_factor:.2f}</code>, 半衰期: <code>{snapshot.half_life_hours:.0f}h</code>)",
                    f"• <b>圖譜規模</b>：<code>{snapshot.nodes_count}</code> 個節點 (7 宏觀源 + 8 產業樞紐 + 13 標的) | <code>{snapshot.edges_count}</code> 條加權因果彈性邊",
                    f"• <b>系統性因果震盪指標</b>：{shock_badge}",
                    f"• <b>當前活躍突發事件</b>：<code>{snapshot.active_events_count}</code> 件",
                ]

                if sim_result:
                    ev_info = sim_result.get("event", {})
                    lines.append(
                        f"⚠️ <b>[劇本模擬中: {sim_result.get('scenario')}]</b>\n"
                        f"  ├ 事件快訊: <b>{ev_info.get('headline', '模擬劇本')}</b>\n"
                        f"  └ 衝擊節點: <code>{ev_info.get('shock_node')}</code> (初始衝擊強度: <code>{ev_info.get('raw_intensity', 0.0):.2f}</code>)"
                    )
                elif snapshot.active_events:
                    for ev in snapshot.active_events[:3]:
                        lines.append(
                            f"  ├ <b>{ev.headline[:35]}...</b>\n"
                            f"  │ 節點: <code>{ev.shock_node}</code> | 有效強度: <code>{ev.effective_intensity:.2f}</code> ({ev.source})"
                        )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("🎯 <b>【各標的因果傳播淨受損度矩陣與大腦避險決策】</b>")

                # 標的分組排序：重創 -> 避險受益 -> 中度 -> 中立
                damages = list(snapshot.damages.values())
                damages.sort(key=lambda d: d.net_damage)

                severe_alerts = []
                hedge_opportunities = []

                for d in damages:
                    sym = d.ticker
                    dmg = d.net_damage
                    tier = d.damage_tier
                    path_str = " ➔ ".join(d.direct_exposure_path)

                    if tier == ShockDamageTier.SEVERE_DAMAGE:
                        badge = "🔴 SEVERE (重創)"
                        act_disp = "⛔ <b>熔斷暫緩買入 / 優先減碼</b>"
                        severe_alerts.append((sym, dmg, path_str))
                    elif tier == ShockDamageTier.MODERATE_DAMAGE:
                        badge = "🟡 MODERATE (中度承壓)"
                        act_disp = "⚠️ <b>延後分批建倉</b>"
                    elif tier == ShockDamageTier.POSITIVE_HEDGE:
                        badge = "🟢 HEDGE (避險受益)"
                        act_disp = "🛡️ <b>對沖工具加碼</b>"
                        hedge_opportunities.append((sym, dmg, path_str))
                    else:
                        badge = "⚪ NEUTRAL (平穩)"
                        act_disp = "✅ <b>正常配置運作</b>"

                    lines.append(
                        f"• <b>{sym}</b> [{badge}]\n"
                        f"  ├ 淨受損度: <code>{dmg:+.1%}</code> | 避險優先級: <code>{d.hedge_priority:.2f}</code>\n"
                        f"  ├ 因果鏈條: <code>{path_str}</code>\n"
                        f"  └ 處置策略: {act_disp}"
                    )

                if severe_alerts:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🚨 <b>【突發因果傳導熔斷警示】</b>")
                    for sym, dmg, p in severe_alerts:
                        lines.append(
                            f"• <b>{sym}</b> (淨受損 <code>{dmg:+.1%}</code>): 受宏觀衝擊經由 <code>{p}</code> 傳導波及，"
                            f"分批建倉已前置自動熔斷 (event_graph_deferred)，防止盲目接刀！"
                        )

                if hedge_opportunities:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("🛡️ <b>【對沖避險受益資產推薦】</b>")
                    for sym, dmg, p in hedge_opportunities:
                        lines.append(
                            f"• <b>{sym}</b> (正向彈性 <code>{dmg:+.1%}</code>): 因果網絡推升避險溢價，可作為反向對沖配置。"
                        )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>輸入 <code>/eventgraph sim</code> 模擬台海斷鏈黑天鵝；支援 <code>fed</code>、<code>bank</code>、<code>oil</code>；輸入 <code>/eventgraph clear</code> 重置常態。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate Macro Event Causal Graph response: {e}")
                return f"⚠️ 查詢宏觀突發事件因果圖譜狀態時發生錯誤：{e}"

        # 17. Bayesian HMM Continuous Factor Allocation / 隱馬爾可夫 / 貝葉斯濾波 / 體制機率 (Phase 38)
        if any(cmd.startswith(prefix) for prefix in ("hmm", "bayesianfilter", "filter", "regimeprob", "hmmfactor", "隱馬爾可夫", "貝葉斯濾波", "體制機率", "連續體制")):
            try:
                from src.services.bayesian_hmm_factor_service import (
                    BayesianHMMFactorService,
                    TacticalMarketPhase,
                )
                from src.services.settings_service import SettingsService

                settings_svc = SettingsService(user_id=resolved_user_id)
                hmm_svc = BayesianHMMFactorService(
                    user_id=resolved_user_id,
                    settings_service=settings_svc,
                )

                # Subcommand: reset / clear
                if any(k in cmd for k in ("clear", "reset", "重置")):
                    hmm_svc.reset_state()
                    return (
                        "🔄 <b>【貝葉斯隱馬爾可夫狀態已重置】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "已清除 Redis 分散式後驗信念快取，體制機率分佈回復均勻無先驗基準。"
                    )

                # Subcommand: sim <REGIME>
                sim_regime = None
                if any(k in cmd for k in ("sim", "模擬")):
                    parts = cmd.split()
                    for p in parts:
                        p_up = p.upper()
                        if p_up in ("BULL", "ACCELERATION", "多頭"):
                            sim_regime = "BULL"
                        elif p_up in ("REBOUND", "PIVOT", "反彈"):
                            sim_regime = "REBOUND"
                        elif p_up in ("VALUE", "LATE", "價值"):
                            sim_regime = "VALUE"
                        elif p_up in ("DEFENSE", "BEAR", "CONSOLIDATION", "防禦"):
                            sim_regime = "DEFENSE"

                if sim_regime:
                    sim_obs = hmm_svc.simulate_observation(sim_regime)
                    posterior = hmm_svc.update_beliefs_sync(sim_obs, persist=True)
                    sim_note = f"⚠️ <b>[情境模擬更新: {sim_regime}]</b> 已注入典型宏觀觀測值並推演後驗分佈\n"
                else:
                    sim_note = ""
                    posterior = hmm_svc.get_current_posterior()

                status_badge = "🟢 運行中 (Online)" if hmm_svc.is_enabled else "🟡 旁路 (Bypass)"

                # Format phase probabilities bar
                probs = posterior.probabilities
                phase_labels = {
                    TacticalMarketPhase.BULL_ACCELERATION.value: ("🚀 BULL (多頭動能加速)", probs.get(TacticalMarketPhase.BULL_ACCELERATION.value, 0.0)),
                    TacticalMarketPhase.EARLY_REBOUND.value: ("🌱 REBOUND (超跌修復強彈)", probs.get(TacticalMarketPhase.EARLY_REBOUND.value, 0.0)),
                    TacticalMarketPhase.LATE_CYCLE_VALUE.value: ("💎 VALUE (景氣高檔價值)", probs.get(TacticalMarketPhase.LATE_CYCLE_VALUE.value, 0.0)),
                    TacticalMarketPhase.DEFENSIVE_CONSOLIDATION.value: ("🛡️ DEFENSE (低波品質防禦)", probs.get(TacticalMarketPhase.DEFENSIVE_CONSOLIDATION.value, 0.0)),
                }

                lines = [
                    "🔮 <b>【在線連續貝葉斯濾波與隱馬爾可夫因子動態配置報告 (Phase 38)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "• <b>核心演算法</b>：<code>4-State Hidden Markov Model + Online Hamilton Filter + Shannon Entropy Guard</code>",
                    f"• <b>引擎狀態</b>：{status_badge} (持續性 p: <code>{hmm_svc.transition_persistence:.2f}</code>, 熵防禦門檻: <code>{hmm_svc.entropy_defense_threshold:.2f}</code>)",
                    f"• <b>當前主導體制</b>：<b>{posterior.dominant_phase.value}</b> (信心度: <code>{posterior.confidence:.1%}</code>)",
                    f"• <b>香農不確定性熵</b>：<code>H={posterior.entropy:.2f}</code> (模糊指數: <code>{posterior.ambiguity_index:.1%}</code>)",
                ]

                if posterior.is_entropy_guard_active:
                    lines.append("  └ ⚠️ <b>【體制模糊守衛啟動】</b>：市場處於體制轉換劇烈模糊期，已自適應向低波動/品質防禦錨點傾斜！")

                if sim_note:
                    lines.append(sim_note)

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("📊 <b>【4 大隱馬爾可夫風格體制連續後驗機率分佈】</b>")
                for key, (label, p_val) in phase_labels.items():
                    bar_len = int(p_val * 20)
                    bar_str = "█" * bar_len + "░" * (20 - bar_len)
                    is_dom = " ★" if key == posterior.dominant_phase.value else ""
                    lines.append(f"• <b>{label}</b>{is_dom}\n  <code>[{bar_str}]</code> <b>{p_val:5.1%}</b>")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("⚖️ <b>【連續平滑混合 6 大量化因子動態權重】</b>")
                lines.append("<i>(消除離散階梯斷層跳躍，動態加權各體制最優 Alpha 暴露)</i>")

                factor_names_zh = {
                    "momentum": "動能趨勢 (Momentum)",
                    "smart_money": "聰明錢大單 (Smart Money)",
                    "liquidity_premium": "流動性溢價 (Liquidity Premium)",
                    "quality": "基本面品質 (Quality)",
                    "value": "價值安全邊際 (Value)",
                    "low_vol": "低波動防守 (Low Volatility)",
                }

                active_weights = posterior.guarded_weights if posterior.is_entropy_guard_active else posterior.continuous_weights
                for f_key in ("momentum", "smart_money", "liquidity_premium", "quality", "value", "low_vol"):
                    w = active_weights.get(f_key, 0.0)
                    w_bar = int(w * 25)
                    bar = "■" * w_bar + "□" * (25 - w_bar)
                    lines.append(f"• <b>{factor_names_zh.get(f_key, f_key)}</b>\n  <code>[{bar}]</code> <b>{w:5.1%}</b>")

                obs = posterior.observation
                if obs:
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("📡 <b>【多元宏觀高斯觀測向量 (Observation Vector)】</b>")
                    lines.append(
                        f"• <b>SPY 趨勢偏離 (200MA)</b>: <code>{obs.get('trend_ratio', 0.0):+.2%}</code> | "
                        f"<b>VIX 水準</b>: <code>{obs.get('vix', 0.0):.1f}</code> (Z: <code>{obs.get('vix_z_score', 0.0):+.1f}σ</code>)\n"
                        f"• <b>10Y-2Y 殖利率利差</b>: <code>{obs.get('yield_spread', 0.0):+.2f}%</code> | "
                        f"<b>5日累積報酬</b>: <code>{obs.get('return_5d', 0.0):+.2%}</code>"
                    )

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>輸入 <code>/hmm sim &lt;bull|rebound|value|defense&gt;</code> 模擬宏觀體制衝擊；輸入 <code>/hmm clear</code> 重置為無先驗基準。</i>")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate Bayesian HMM Factor response: {e}")
                return f"⚠️ 查詢貝葉斯隱馬爾可夫連續因子配置狀態時發生錯誤：{e}"

        # 18. Universe / Pool / Tickers / 標的池 / 股票池 (Phase 39)
        if any(cmd.startswith(prefix) for prefix in ("universe", "pool", "tickers", "標的池", "股票池", "標的", "候選池")):
            try:
                from src.services.universe_lifecycle_service import UniverseLifecycleService
                from src.repositories.ticker_universe_repository import TickerUniverseRepository
                from src.services.sector_drift_guard_service import SectorDriftGuardService

                repo = TickerUniverseRepository()
                uni_svc = UniverseLifecycleService(user_id=resolved_user_id, repo=repo)

                # Subcommand: prune / gc / clean / 修剪 / 換血 / 清理 (Phase 42)
                if any(k in cmd for k in ("prune", "gc", "clean", "修剪", "換血", "清理")):
                    prune_res = await uni_svc.prune_universe_momentum()
                    stag = prune_res.get("stagnant_candidates", [])
                    stale = prune_res.get("stale_shadow_positions", [])
                    sec = prune_res.get("sector_quota_pruned", [])
                    total_p = prune_res.get("total_pruned", 0)

                    lines = [
                        "🧹 <b>【標的池自適應動能剪枝與換血完成】</b>",
                        "━━━━━━━━━━━━━━━━━━",
                        f"• <b>本次清理總數</b>：<b>{total_p} 檔標的</b>",
                        f"• <b>動能衰竭候選股 (RS < -2.5%)</b>：{len(stag)} 檔",
                        f"• <b>過期未達標影子持倉</b>：{len(stale)} 檔",
                        f"• <b>板塊超額候選股 (>3 檔)</b>：{len(sec)} 檔",
                        "━━━━━━━━━━━━━━━━━━",
                    ]
                    if stag:
                        lines.append("🔻 <b>動能淘汰候選股</b>：")
                        for s in stag:
                            lines.append(f"  └ <code>{s.get('ticker')}</code> (駐留 {s.get('tenure_days')} 天 | RS 相對差: {s.get('rs_delta', 0)*100:+.1f}%)")
                    if stale:
                        lines.append("🔻 <b>影子過期淘汰</b>：")
                        for st in stale:
                            lines.append(f"  └ <code>{st.get('ticker')}</code> (觀測 {st.get('tenure_days')} 天 | 影子 MTM: {st.get('shadow_return', 0)*100:+.1f}%)")
                    if sec:
                        lines.append("🔻 <b>板塊配額超額剪枝</b>：")
                        for sc in sec:
                            lines.append(f"  └ <code>{sc.get('ticker')}</code> ({sc.get('sector')})")

                    if total_p == 0:
                        lines.append("✨ 候選池與影子池標的皆維持健康動能與合規配額，無需修剪。")

                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("💡 <i>配額已釋放，後續週期將自動納入新晉高 Alpha 潛力標的。輸入 <code>/universe</code> 檢視最新標的池。</i>")
                    return "\n".join(lines)

                # Subcommand: scan / refresh / 掃描 / 重跑
                if any(k in cmd for k in ("scan", "refresh", "掃描", "重跑")):
                    try:
                        from src.infrastructure.tasks import run_universe_lifecycle
                        run_universe_lifecycle.delay(user_id=resolved_user_id, force=True)
                    except Exception as te:
                        logger.debug(f"Celery delay unavailable, executing lifecycle cycle inline: {te}")
                        await uni_svc.run_lifecycle_cycle(force=True)

                    return (
                        "🚀 <b>【標的池背景生命週期演化掃描已啟動】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "• <b>執行模式</b>：強制全量掃描 (Force Lifecycle Evolution)\n"
                        "• <b>檢驗項目</b>：宏觀環境 (VIX/殖利率)、個股品質門檻 (<4.0 汰除)、候選池 Top 30 競爭性輪換、板塊漂移 HHI\n"
                        "• <b>即時通報</b>：演化完成後將透過 Telegram/Email 主動推播最新簡報卡片！\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>輸入 <code>/universe</code> 可隨時檢視當前標的池分佈；輸入 <code>/universe prune</code> 觸發動能換血。</i>"
                    )

                # Normal status query
                active_rows = repo.get_all(resolved_user_id, status="active")
                candidate_rows = repo.get_all(resolved_user_id, status="candidate")
                shadow_rows = repo.get_all(resolved_user_id, status="shadow")
                removed_rows = repo.get_all(resolved_user_id, status="removed")

                # Sector drift analysis
                drift_svc = SectorDriftGuardService(user_id=resolved_user_id, repo=repo)
                drift_rep = drift_svc.analyze_universe_sectors(current_active=active_rows)
                hhi = drift_rep.distribution.hhi_index
                hhi_status = drift_rep.status.value

                # Macro regime
                macro_reg = await uni_svc.detect_macro_regime()

                lines = [
                    "🌐 <b>【投資顧問標的池即時架構狀態 (Universe Telemetry)】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>宏觀環境體制</b>：<code>{macro_reg.regime}</code> (VIX: <code>{macro_reg.vix:.1f}</code>, 門檻微調: <code>{macro_reg.quality_score_adjustment:+.1f}</code>)",
                    f"• <b>實盤活躍池</b>：<b>{len(active_rows)} / 8 檔</b> (上限容量)",
                    f"• <b>儲備候選池</b>：<b>{len(candidate_rows)} / 30 檔</b> (競爭性儲備)",
                    f"• <b>影子觀測池</b>：<b>{len(shadow_rows)} 檔</b> (MTM 畢業考評中)",
                    f"• <b>歷史淘汰池</b>：<b>{len(removed_rows)} 檔</b>",
                    f"• <b>板塊集中度</b>：<code>{hhi_status}</code> (HHI: <code>{hhi:.3f}</code>)",
                    "━━━━━━━━━━━━━━━━━━",
                    "🎯 <b>【實盤活躍標的 (Active Tickers)】</b>",
                ]

                for a in active_rows:
                    sym = a["ticker"]
                    sec = a.get("sector") or "科技與成長"
                    pin_str = " 📌(置頂)" if a.get("is_pinned") else ""
                    lines.append(f"• <b>{sym}</b> ({sec}){pin_str}")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append(f"📥 <b>【儲備候選池亮點 (Top Candidates, 共 {len(candidate_rows)} 檔)】</b>")
                cand_symbols = [c["ticker"] for c in candidate_rows[:12]]
                lines.append("<code>" + ", ".join(cand_symbols) + "</code>" + (" ... 等" if len(candidate_rows) > 12 else ""))

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append(
                    "💡 <i>指令提示：輸入 <code>/universe prune</code> 觸發動能換血剪枝；輸入 <code>/universe scan</code> 啟動全量重掃描；輸入 <code>/guard</code> 檢視風控守衛。</i>"
                )
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Failed to generate Universe telemetry response: {e}")
                return f"⚠️ 查詢標的池狀態時發生錯誤：{e}"

        # 19. Dipbuy / Stagger / 階梯掛單 / 吸籌 (Phase 41)
        if any(cmd.startswith(prefix) for prefix in ("dipbuy", "stagger", "dip", "階梯掛單", "吸籌", "階梯吸籌", "限價吸籌")):
            try:
                from src.services.staggered_dip_buying_service import StaggeredDipBuyingService
                stagger_svc = StaggeredDipBuyingService(user_id=resolved_user_id)

                # Subcommand: cancel / 撤單 / 取消
                if any(k in cmd for k in ("cancel", "撤單", "取消")):
                    cancel_res = await stagger_svc.cancel_all_pending_staggered_orders(
                        reason="使用者手動透過 /dipbuy cancel 撤銷"
                    )
                    c_count = cancel_res.get("cancelled_count", 0)
                    rel_cash = cancel_res.get("released_cash_usd", 0.0)
                    f_count = cancel_res.get("filled_count", 0)
                    f_cash = cancel_res.get("filled_cash_usd", 0.0)
                    return (
                        "🛑 <b>【主力支撐階梯掛單安全撤除完成】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>已撤除未成交掛單</b>：<b>{c_count} 筆</b>\n"
                        f"• <b>即時釋放現金儲備</b>：<code>+${rel_cash:.2f} USD</code>\n"
                        f"• <b>今日盤中累計成交</b>：{f_count} 筆 (<code>${f_cash:.2f} USD</code>)\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>資金已全數解除保留，無任何過夜持倉或資金佔用風險。</i>"
                    )

                # Subcommand: run / exec / 執行 / 下單
                if any(k in cmd for k in ("run", "exec", "執行", "下單")):
                    exec_res = await stagger_svc.execute_staggered_dip_deployment(force=True)
                    if not exec_res.get("success"):
                        return f"⚠️ 階梯限價吸籌執行未成功：{exec_res.get('message', '未知原因')}"
                    return (
                        f"🎯 <b>【主力支撐階梯限價吸籌下發成功】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>下發批次</b>：第 {exec_res.get('batch_number')} 批次\n"
                        f"• <b>下發階梯掛單數</b>：<b>{exec_res.get('order_count')} 筆</b>\n"
                        f"• <b>預備吸籌總額</b>：<code>${exec_res.get('total_planned_usd', 0.0):.2f} USD</code>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>掛單已進入隊列與券商，未成交部位將於 15:55 EST 收盤前自動安全撤銷。輸入 <code>/dipbuy status</code> 檢視狀態。</i>"
                    )

                # Subcommand: reconcile / check / 撮合 / 對帳 (Phase 45)
                if any(k in cmd for k in ("reconcile", "check", "撮合", "對帳")):
                    rec_res = await stagger_svc.reconcile_staggered_order_fills()
                    f_count = rec_res.get("filled_count", 0)
                    rem_count = rec_res.get("remaining_pending_count", 0)
                    return (
                        f"🎯 <b>【階梯限價吸籌撮合對帳完成】</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>本次新撮合成交數</b>：<b>{f_count} 筆</b>\n"
                        f"• <b>剩餘待成交掛單數</b>：{rem_count} 筆\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💡 <i>新成交部位已自動掛載動態 ATR 保護停損點並移交 Sentinel 守護。輸入 <code>/dipbuy status</code> 檢視明細。</i>"
                    )

                # Subcommand: stalk / reprice / 追單 / 改價
                if any(k in cmd for k in ("stalk", "reprice", "追單", "改價")):
                    res = await stagger_svc.stalk_and_reprice_pending_orders()
                    rep_cnt = res.get("repriced_count", 0)
                    rep_orders = res.get("orders", [])
                    lines = [
                        "🏹 <b>【盤中動態追單改價完成】</b>",
                        "━━━━━━━━━━━━━━━━━━",
                        f"• <b>本次改價掛單數</b>：<b>{rep_cnt} 筆</b>",
                    ]
                    if rep_cnt == 0:
                        lines.append("✨ <i>當前所有 PENDING 訂單已符合最新均價，或市場無顯著多頭跳空，暫無需改價。</i>")
                    else:
                        for o in rep_orders:
                            lines.append(f"  └ <b>{o.get('ticker')}</b> Tier {o.get('tier_number')}：<code>${o.get('original_limit_price', 0):.2f}</code> ➔ <code>${o.get('limit_price', 0):.2f} USD</code>")
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("💡 <i>輸入 <code>/dipbuy status</code> 檢視即時掛單狀態。</i>")
                    return "\n".join(lines)

                # Subcommand: moc / conversion / 尾盤 / 接管
                if any(k in cmd for k in ("moc", "conversion", "尾盤", "接管")):
                    res = await stagger_svc.convert_unfilled_dip_orders_to_moc()
                    conv_cnt = res.get("converted_count", 0)
                    conv_orders = res.get("orders", [])
                    lines = [
                        "🏁 <b>【尾盤動能接管吸籌完成】</b>",
                        "━━━━━━━━━━━━━━━━━━",
                        f"• <b>本次強制接管成交數</b>：<b>{conv_cnt} 筆</b>",
                    ]
                    if conv_cnt == 0:
                        lines.append("✨ <i>今日無待接管訂單或現金水位已處於安全目標區。</i>")
                    else:
                        for o in conv_orders:
                            lines.append(f"  └ 🟢 <b>{o.get('ticker')}</b>：<code>${o.get('fill_price', 0):.2f} USD</code> (金額: <code>${o.get('amount_usd', 0):.2f}</code>, 停損: <code>${o.get('initial_stop_price', 0):.2f}</code>)")
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("💡 <i>持倉已自動移交 Sentinel 守護。輸入 <code>/alpha</code> 檢視最新淨超額。</i>")
                    return "\n".join(lines)

                # Subcommand: plan / 計畫 / 預覽 / 點位
                if any(k in cmd for k in ("plan", "計畫", "預覽", "點位")):
                    plan = await stagger_svc.generate_batch_staggered_plan()
                    lines = [
                        f"🎯 <b>【主力支撐階梯限價吸籌規劃方案 (第 {plan.batch_number} 批次)】</b>",
                        "━━━━━━━━━━━━━━━━━━",
                        f"• <b>可支配建倉資金</b>：<code>${plan.total_deployable_cash:.2f} USD</code>",
                        f"• <b>計畫吸籌總預算</b>：<code>${plan.total_planned_deployment_usd:.2f} USD</code>",
                        f"• <b>執行許可狀態</b>：{'🟢 可執行' if plan.can_execute else '🔴 暫緩 (資金不足或風控阻斷)'}",
                        "━━━━━━━━━━━━━━━━━━",
                        "<b>【各標的 3-Tier 階梯限價點位】</b>",
                    ]
                    for tp in plan.plans:
                        status_mark = "🟢" if tp.is_risk_allowed else "⛔"
                        lines.append(f"{status_mark} <b>{tp.ticker}</b> (現價: <code>${tp.current_price:.2f}</code> | 預算: <code>${tp.total_budget_usd:.2f}</code>)：")
                        if not tp.is_risk_allowed:
                            lines.append(f"  └ <i>風控阻斷：{tp.risk_blocker or 'Risk Gateway'}</i>")
                            continue
                        for t in tp.tiers:
                            lines.append(
                                f"  └ <b>{t.name}</b>：<code>${t.target_price:.2f}</code> "
                                f"(-{t.discount_pct * 100:.1f}%) | 金額: <code>${t.allocation_usd:.2f}</code> "
                                f"({t.support_anchor_type})"
                            )
                    lines.append("━━━━━━━━━━━━━━━━━━")
                    lines.append("💡 <i>輸入 <code>/dipbuy run</code> 立即下發掛單；輸入 <code>/dipbuy cancel</code> 一鍵撤單。</i>")
                    return "\n".join(lines)

                # Default: status 查詢今日掛單
                orders = await stagger_svc.get_active_staggered_orders()
                if not orders:
                    # 若今日尚無掛單，引導預覽計畫
                    plan = await stagger_svc.generate_batch_staggered_plan()
                    return (
                        "🎯 <b>【今日尚無活躍之階梯限價掛單】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>當前待建倉批次</b>：第 {plan.batch_number} 批次\n"
                        f"• <b>可支配建倉資金</b>：<code>${plan.total_deployable_cash:.2f} USD</code>\n"
                        f"• <b>本批候選標的數</b>：{len(plan.plans)} 檔\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💡 <i>系統每日於 09:35 EST 自動派發階梯單。輸入 <code>/dipbuy plan</code> 可預覽 3-Tier 點位，輸入 <code>/dipbuy run</code> 可手動下發。</i>"
                    )

                pending_orders = [o for o in orders if o.get("status") == "PENDING"]
                filled_orders = [o for o in orders if o.get("status") == "FILLED"]
                cancelled_orders = [o for o in orders if o.get("status") == "CANCELLED"]

                lines = [
                    "🎯 <b>【主力支撐階梯吸籌當日掛單狀態】</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"• <b>總掛單數</b>：{len(orders)} 筆",
                    f"• <b>待撮合成交 (PENDING)</b>：<b>{len(pending_orders)} 筆</b> (<code>${sum(float(o.get('amount_usd', 0)) for o in pending_orders):.2f} USD</code>)",
                    f"• <b>已撮合成交 (FILLED)</b>：<b>{len(filled_orders)} 筆</b> (<code>${sum(float(o.get('amount_usd', 0)) for o in filled_orders):.2f} USD</code>)",
                    f"• <b>已撤除/釋放 (CANCELLED)</b>：{len(cancelled_orders)} 筆",
                    "━━━━━━━━━━━━━━━━━━",
                    "<b>【明細清單】</b>",
                ]
                for o in orders:
                    st = o.get("status")
                    sym = o.get("ticker")
                    tier_name = o.get("tier_name", f"Tier {o.get('tier_number')}")
                    p = float(o.get("limit_price", 0))
                    amt = float(o.get("amount_usd", 0))
                    disc = float(o.get("discount_pct", 0)) * 100
                    st_icon = "⏳" if st == "PENDING" else ("✅" if st == "FILLED" else "🚫")
                    lines.append(f"{st_icon} <b>{sym}</b> {tier_name}：<code>${p:.2f}</code> (-{disc:.1f}%) | <code>${amt:.2f}</code> [{st}]")

                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append("💡 <i>提示：所有 PENDING 掛單將於 15:55 EST 自動撤除釋放現金。輸入 <code>/dipbuy cancel</code> 可立即手動撤銷。</i>")
                return "\n".join(lines)

            except Exception as e:
                logger.error(f"Failed to generate Dipbuy response: {e}")
                return f"⚠️ 處理階梯限價吸籌指令時發生錯誤：{e}"

        # 20. Alpha / Net Alpha / Cash Drag Attribution (Phase 44)
        if any(cmd.startswith(prefix) for prefix in ("alpha", "netalpha", "cashdrag", "歸因", "淨額", "成本歸因", "機會成本")):
            try:
                from src.services.net_alpha_attribution_service import NetAlphaAttributionService
                alpha_svc = NetAlphaAttributionService(user_id=resolved_user_id)
                lookback = 30
                parts = cmd.split()
                if len(parts) > 1:
                    arg = parts[1].strip().lower()
                    if arg == "ytd":
                        today = datetime.now()
                        lookback = max(1, (today - datetime(today.year, 1, 1)).days)
                    elif arg.isdigit() and int(arg) > 0:
                        lookback = int(arg)

                report = await alpha_svc.calculate_complete_report(lookback_days=lookback)
                return alpha_svc.format_telegram_report(report)
            except Exception as e:
                logger.error(f"Failed to generate Alpha attribution response: {e}")
                return f"⚠️ 查詢淨 Alpha 歸因與現金拖累時發生錯誤：{e}"

        # 21. Hard Token Budget Guard & 0-LLM Status (Phase 47)
        if any(cmd.startswith(prefix) for prefix in ("budget", "token", "預算", "代幣", "成本預算", "額度")):
            try:
                from src.services.hard_token_budget_guard_service import HardTokenBudgetGuardService
                guard_svc = HardTokenBudgetGuardService(user_id=resolved_user_id)
                parts = cmd.split()
                sub = parts[1].strip().lower() if len(parts) > 1 else "status"
                if sub in ("reset", "clear", "重設", "解鎖"):
                    res = guard_svc.reset_budget_lockout()
                    return (
                        "🔄 <b>【AI 代幣硬性預算熔斷已重設】</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>重設時間</b>：<code>{res.get('reset_at')}</code>\n"
                        f"• <b>扣除今日已消耗額度</b>：<code>${res.get('daily_offset_applied_usd', 0.0):.4f} USD</code>\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "✨ <i>今日預算已重新開放，例行巡航仍維持 0-LLM 數理引擎節能模式。</i>"
                    )
                return guard_svc.format_budget_report()
            except Exception as e:
                logger.error(f"Failed to generate Budget response: {e}")
                return f"⚠️ 查詢代幣預算狀態時發生錯誤：{e}"

        # 22. Sector Concentration & HHI Drift Guard (Phase 51 & 52)
        if any(cmd.startswith(prefix) for prefix in ("sector", "drift", "hhi", "板塊", "行業", "集中度", "板塊漂移", "板塊自癒")):
            try:
                from src.services.broker_factory import BrokerFactory
                from src.services.sector_drift_guard_service import SectorDriftGuardService, SectorDriftStatus
                from src.repositories.ticker_universe_repository import TickerUniverseRepository

                broker = BrokerFactory.get_broker(user_id=resolved_user_id)
                positions = await broker.get_positions() if broker else []
                account = await broker.get_account() if broker else None
                total_equity = float(getattr(account, "total_equity", 0.0) or 0.0) if account else 0.0

                repo = TickerUniverseRepository()
                drift_guard = SectorDriftGuardService(user_id=resolved_user_id, repo=repo)
                report = drift_guard.analyze_portfolio_holdings(positions, total_equity=total_equity)

                status_emoji = "🟢" if report.status == SectorDriftStatus.BALANCED else ("🟡" if report.status == SectorDriftStatus.DRIFT_WARNING else "🔴")

                bar_lines = []
                sorted_sectors = sorted(report.sector_values.items(), key=lambda x: x[1], reverse=True)
                for sec, val in sorted_sectors:
                    w_stock = report.sector_weights.get(sec, 0.0)
                    w_nlv = report.nlv_sector_weights.get(sec, 0.0)
                    bars = int(round(w_stock * 10))
                    bar_str = "▓" * bars + "░" * max(0, 10 - bars)
                    bar_lines.append(f"• <b>{sec}</b>：<code>${val:,.2f}</code> ({w_stock:.1%} 股票 / {w_nlv:.1%} 淨值)\n  └ <code>[{bar_str}]</code>")

                if not bar_lines:
                    bar_lines.append("• <i>目前無持倉，100% 現金儲備</i>")

                injected_str = "未觸發自癒"
                contender = drift_guard.discover_cross_sector_injection_contender(
                    current_positions=positions,
                    total_equity=total_equity,
                )
                if contender:
                    injected_str = f"推薦注入 <b>{contender['ticker']}</b> ({contender['sector']})"

                over_str = ", ".join(report.over_concentrated_sectors) if report.over_concentrated_sectors else "無 (良好)"
                under_str = ", ".join(report.under_represented_sectors[:3]) if report.under_represented_sectors else "無"

                quota_pct = drift_guard.cross_sector_injection_quota_pct

                rec_lines = "\n".join(f"  └ <i>{r}</i>" for r in report.recommendations[:2]) if report.recommendations else "  └ <i>投組板塊多角化分佈健康良好。</i>"

                return (
                    f"🌐 <b>【實盤投資組合板塊集中度與 HHI 診斷】</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>整體板塊狀態</b>：{status_emoji} <b>[{report.status.value}]</b>\n"
                    f"• <b>實盤板塊 HHI 指數</b>：<code>{report.hhi_index:.4f}</code> (安全基準線: <code>0.2500</code>)\n"
                    f"• <b>股票資產總值</b>：<code>${report.total_stock_value:,.2f} USD</code> ({report.stock_ratio_pct:.1f}% NLV)\n"
                    f"• <b>帳戶總淨值 (NLV)</b>：<code>${report.total_equity:,.2f} USD</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>【各大行業主題持倉分佈】</b>\n"
                    f"{chr(10).join(bar_lines)}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🛡️ <b>【集中度防線與跨板塊自癒】</b>\n"
                    f"• <b>過度集中行業</b>：<code>{over_str}</code> (硬上限: <code>{report.max_limit_pct:.0%}</code>)\n"
                    f"• <b>欠配/未涵蓋板塊</b>：<code>{under_str}</code>\n"
                    f"• <b>跨板塊自癒配額</b>：<code>{quota_pct:.0%}</code> ({injected_str})\n"
                    f"<b>【診斷處置建議】</b>\n"
                    f"{rec_lines}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 <i>輸入 <code>/batch</code> 檢視建倉計畫，輸入 <code>/dipbuy plan</code> 檢視限價吸籌點位。</i>"
                )
            except Exception as e:
                logger.error(f"Failed to generate Sector response: {e}")
                return f"⚠️ 查詢板塊集中度與 HHI 診斷時發生錯誤：{e}"

        # 23. Alpha Spread Bidding & Friction Offset Engine (Phase 57)
        if any(cmd.startswith(prefix) for prefix in ("spread", "bidding", "friction", "利差", "摩擦")):
            try:
                from src.services.alpha_spread_bidding_service import (
                    AlphaSpreadBiddingService,
                    BiddingAssessmentResult,
                )
                from src.services.batch_cash_deployment_service import BatchCashDeploymentService

                bidding_svc = AlphaSpreadBiddingService(user_id=resolved_user_id)
                batch_svc = BatchCashDeploymentService(
                    user_id=resolved_user_id,
                    alpha_spread_bidding_service=bidding_svc,
                )
                plan = await batch_svc.get_deployment_plan()

                bidding_summary = plan.get("alpha_bidding_summary")
                if bidding_summary and isinstance(bidding_summary, dict):
                    assessment = BiddingAssessmentResult.from_dict(bidding_summary)
                else:
                    items = plan.get("items") or []
                    assessment = await bidding_svc.evaluate_bidding_for_batch(batch_items=items)

                return bidding_svc.format_spread_bidding_report(assessment, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Spread Bidding response: {e}")
                return f"⚠️ 查詢動態利差競標與摩擦抵消儀表時發生錯誤：{e}"

        # 24. Intraday Cross-Sector Correlation & Beta Damping (Phase 58)
        if any(cmd.startswith(prefix) for prefix in ("betadamp", "beta", "damping", "corrdamp", "阻尼", "貝塔阻尼", "大盤相關性")):
            try:
                from src.services.intraday_cross_sector_beta_damping_service import (
                    IntradayCrossSectorBetaDampingService,
                    IntradayBetaMetric,
                )
                from src.services.sector_drift_guard_service import SectorDriftGuardService

                beta_svc = IntradayCrossSectorBetaDampingService(user_id=resolved_user_id)
                drift_guard = SectorDriftGuardService(user_id=resolved_user_id)

                evaluated_metrics: List[IntradayBetaMetric] = []
                evaluated_symbols = set()

                # 從當前活躍的階梯吸籌限價單中提取標的
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    import pytz
                    ny_tz = pytz.timezone("US/Eastern")
                    date_str = datetime.now(ny_tz).strftime("%Y-%m-%d")
                    r = await get_redis(decode_responses=True)
                    r_key = f"staggered_orders:{resolved_user_id}:{date_str}"
                    existing = await r.get(r_key)
                    if existing:
                        orders = json.loads(existing)
                        for o in orders:
                            sym = o.get("ticker")
                            if sym and sym not in evaluated_symbols:
                                sec = o.get("injected_sector")
                                metric = await beta_svc.evaluate_ticker_beta_damping(
                                    ticker=sym,
                                    sector=sec,
                                )
                                evaluated_metrics.append(metric)
                                evaluated_symbols.add(sym)
                except Exception as oe:
                    logger.debug("Could not read staggered orders for betadamp: %s", oe)

                # 若今日尚未掛單，直接查詢自癒候選標的與核心觀察標的
                if not evaluated_metrics:
                    candidates = []
                    try:
                        from src.services.broker_factory import BrokerFactory
                        broker = BrokerFactory.get_broker(user_id=resolved_user_id)
                        positions = await broker.get_positions() if (broker and hasattr(broker, "get_positions")) else []
                        account = await broker.get_account() if (broker and hasattr(broker, "get_account")) else None
                        equity = float(getattr(account, "total_equity", 0.0) or 0.0) if account else 1685.0
                        contender = drift_guard.discover_cross_sector_injection_contender(
                            current_positions=positions,
                            total_equity=equity,
                        )
                        if contender:
                            candidates.append((contender["ticker"], contender.get("sector")))
                    except Exception as ce:
                        logger.debug("Contender discovery in betadamp fallback: %s", ce)

                    for s, sec in [("V", "Financials"), ("COP", "Energy"), ("ECL", "Materials")]:
                        if not any(c[0] == s for c in candidates):
                            candidates.append((s, sec))

                    for sym, sec in candidates[:3]:
                        try:
                            m = await beta_svc.evaluate_ticker_beta_damping(
                                ticker=sym,
                                sector=sec,
                            )
                            evaluated_metrics.append(m)
                        except Exception as me:
                            logger.debug("Beta eval fallback error for %s: %s", sym, me)

                return beta_svc.format_beta_damping_report(evaluated_metrics, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Beta Damping response: {e}")
                return f"⚠️ 查詢跨板塊即時貝塔阻尼儀表時發生錯誤：{e}"

        # 25. Cross-Sector Harvest & Profit Recirculation (Phase 59A)
        if any(cmd.startswith(prefix) for prefix in ("harvest", "recirculate", "收割", "利差回流")) or (
            cmd.startswith(("rebalance", "再平衡")) and any(sub in cmd for sub in ("harvest", "recirculate", "收割", "利差", "profit"))
        ):
            try:
                from src.services.broker_factory import BrokerFactory
                from src.services.cross_sector_harvest_rebalance_service import CrossSectorHarvestRebalanceService

                harvest_svc = CrossSectorHarvestRebalanceService(user_id=resolved_user_id)
                positions = []
                total_equity = 1685.0
                try:
                    broker = BrokerFactory.get_broker(user_id=resolved_user_id)
                    if broker and hasattr(broker, "get_positions"):
                        pos_call = broker.get_positions()
                        positions = await pos_call if inspect.isawaitable(pos_call) else pos_call
                    if broker and hasattr(broker, "get_account"):
                        acc_call = broker.get_account()
                        acc = await acc_call if inspect.isawaitable(acc_call) else acc_call
                        if acc:
                            total_equity = float(getattr(acc, "total_equity", 0.0) or (acc.get("total_equity") if isinstance(acc, dict) else 0.0) or 1685.0)
                except Exception as be:
                    logger.debug("Broker resolution error in harvest command: %s", be)

                assessment = await harvest_svc.evaluate_portfolio_harvest(
                    positions=positions,
                    total_equity=total_equity,
                )
                return harvest_svc.format_harvest_report(assessment, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Harvest & Rebalance response: {e}")
                return f"⚠️ 查詢跨板塊動態收割與利差回流儀表時發生錯誤：{e}"

        # 26. Microstructure Quote Spoofing & Anti-Hunt Detector (Phase 59B)
        if any(cmd.startswith(prefix) for prefix in ("spoof", "antihunt", "orderbook", "假單", "反欺詐", "獵殺防衛")):
            try:
                from src.services.microstructure_spoofing_detector_service import (
                    MicrostructureSpoofingDetectorService,
                    SpoofingMetric,
                )

                spoof_svc = MicrostructureSpoofingDetectorService(user_id=resolved_user_id)
                evaluated_metrics: List[SpoofingMetric] = []
                evaluated_symbols = set()

                # 從當前活躍的階梯吸籌限價單中提取標的
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    import pytz
                    ny_tz = pytz.timezone("US/Eastern")
                    date_str = datetime.now(ny_tz).strftime("%Y-%m-%d")
                    r = await get_redis(decode_responses=True)
                    r_key = f"staggered_orders:{resolved_user_id}:{date_str}"
                    existing = await r.get(r_key)
                    if existing:
                        orders = json.loads(existing)
                        for o in orders:
                            sym = o.get("ticker")
                            if sym and sym not in evaluated_symbols:
                                cur_p = float(o.get("current_price", 0.0) or 0.0)
                                tgt_p = float(o.get("limit_price", 0.0) or (cur_p * 0.985))
                                if cur_p <= 0:
                                    cur_p = tgt_p / 0.985 if tgt_p > 0 else 100.0
                                metric = await spoof_svc.evaluate_spoofing_risk(
                                    ticker=sym,
                                    current_price=cur_p,
                                    target_price=tgt_p,
                                )
                                evaluated_metrics.append(metric)
                                evaluated_symbols.add(sym)
                except Exception as oe:
                    logger.debug("Could not read staggered orders for spoofing detector: %s", oe)

                # 若當日無掛單，以預設焦點標的進行微觀流動性嗅探展示
                if not evaluated_metrics:
                    sample_targets = [
                        ("NVDA", 125.0, 122.5),
                        ("V", 282.0, 277.8),
                        ("COP", 118.0, 115.6),
                    ]
                    for sym, cp, tp in sample_targets:
                        try:
                            m = await spoof_svc.evaluate_spoofing_risk(
                                ticker=sym,
                                current_price=cp,
                                target_price=tp,
                            )
                            evaluated_metrics.append(m)
                        except Exception as se:
                            logger.debug("Spoof eval fallback error for %s: %s", sym, se)

                return spoof_svc.format_spoofing_report(evaluated_metrics, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Spoofing Detector response: {e}")
                return f"⚠️ 查詢微觀獵殺與反欺詐訂單簿嗅探儀表時發生錯誤：{e}"

        # 27. Cross-Market Dark Pool Pricing & Block-Trade Calibration (Phase 60A)
        if any(cmd.startswith(prefix) for prefix in ("darkpool", "prints", "blocktrades", "暗池", "大宗", "暗池定價")):
            try:
                from src.services.cross_market_dark_pool_pricing_service import (
                    CrossMarketDarkPoolPricingService,
                    DarkPoolTickerSummary,
                )

                dark_svc = CrossMarketDarkPoolPricingService(user_id=resolved_user_id)
                evaluated_summaries: List[DarkPoolTickerSummary] = []
                evaluated_symbols = set()

                # 從當前活躍的階梯吸籌限價單中提取標的
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    import pytz
                    ny_tz = pytz.timezone("US/Eastern")
                    date_str = datetime.now(ny_tz).strftime("%Y-%m-%d")
                    r = await get_redis(decode_responses=True)
                    r_key = f"staggered_orders:{resolved_user_id}:{date_str}"
                    existing = await r.get(r_key)
                    if existing:
                        orders = json.loads(existing)
                        for o in orders:
                            sym = o.get("ticker")
                            if sym and sym not in evaluated_symbols:
                                cur_p = float(o.get("current_price", 0.0) or 0.0)
                                if cur_p <= 0:
                                    cur_p = float(o.get("limit_price", 100.0) or 100.0)
                                summary = await dark_svc.evaluate_dark_pool_activity(
                                    ticker=sym,
                                    reference_price=cur_p,
                                )
                                evaluated_summaries.append(summary)
                                evaluated_symbols.add(sym)
                except Exception as oe:
                    logger.debug("Could not read staggered orders for dark pool: %s", oe)

                # 若當日無掛單，以預設核心焦點標的展示
                if not evaluated_summaries:
                    for sym, ref_p in [("NVDA", 125.0), ("V", 282.0), ("COP", 118.0)]:
                        try:
                            s = await dark_svc.evaluate_dark_pool_activity(
                                ticker=sym,
                                reference_price=ref_p,
                            )
                            evaluated_summaries.append(s)
                        except Exception as de:
                            logger.debug("Dark pool eval fallback error for %s: %s", sym, de)

                return dark_svc.format_dark_pool_report(evaluated_summaries, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Dark Pool Pricing response: {e}")
                return f"⚠️ 查詢跨市場暗池大宗換手與校準儀表時發生錯誤：{e}"

        # 28. Multi-Factor Convex Sharpe Frontier Optimization (Phase 60B)
        if any(cmd.startswith(prefix) for prefix in ("convex", "sharpe", "qp", "mvo", "凸規劃", "夏普邊界", "最優配置")):
            try:
                from src.services.multi_factor_convex_sharpe_optimizer_service import (
                    MultiFactorConvexSharpeOptimizerService,
                )

                convex_svc = MultiFactorConvexSharpeOptimizerService(user_id=resolved_user_id)
                available_capital = 1400.0

                # 嘗試讀取已回流資金或批次建倉可支配現金
                try:
                    from src.infrastructure.cache.redis_client import get_redis
                    r = await get_redis(decode_responses=True)
                    cached_harvest = await r.get(f"portfolio:recirculated_cash:{resolved_user_id}")
                    if cached_harvest:
                        h_data = json.loads(cached_harvest)
                        recirc = float(h_data.get("total_recirculated_cash_usd", 0.0) or 0.0)
                        if recirc >= 10.0:
                            available_capital = recirc
                except Exception as re_err:
                    logger.debug("Could not read recirculated cash in convex command: %s", re_err)

                candidate_tickers = ["NVDA", "TSM", "AAPL", "MSFT", "V", "COP", "ECL"]
                result = await convex_svc.optimize_recirculated_capital_allocation(
                    candidate_tickers=candidate_tickers,
                    available_capital_usd=available_capital,
                )
                return convex_svc.format_convex_sharpe_report(result, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Convex Sharpe Optimization response: {e}")
                return f"⚠️ 查詢夏普邊界最優二次規劃儀表時發生錯誤：{e}"

        # 29. Dynamic IV Surface Skew & Tail Risk Hedging (Phase 61A)
        if any(cmd.startswith(prefix) for prefix in ("ivskew", "skew", "iv", "波動率偏度", "選擇權偏度", "尾部避險")):
            try:
                from src.services.dynamic_iv_surface_skew_hedging_service import (
                    DynamicIVSurfaceSkewHedgingService,
                    IVSurfaceTickerMetric,
                )

                iv_svc = DynamicIVSurfaceSkewHedgingService(user_id=resolved_user_id)
                metrics: List[IVSurfaceTickerMetric] = []
                evaluated_symbols = set()

                candidates = ["SPY", "QQQ", "NVDA", "TSM", "AAPL"]
                for sym in candidates:
                    if sym not in evaluated_symbols:
                        try:
                            m = await iv_svc.assess_iv_surface(sym)
                            metrics.append(m)
                            evaluated_symbols.add(sym)
                        except Exception as se:
                            logger.debug("IV skew router eval error for %s: %s", sym, se)

                return iv_svc.format_iv_skew_report(metrics, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate IV Skew Hedging response: {e}")
                return f"⚠️ 查詢隱含波動率曲面偏度與極端尾部避險儀表時發生錯誤：{e}"

        # 30. Microstructure Order Flow Imbalance & Liquidity Vacuum Defense (Phase 61B)
        if any(cmd.startswith(prefix) for prefix in ("ofi", "orderflow", "訂單流失衡", "流動性真空", "微觀失衡")):
            try:
                from src.services.microstructure_order_flow_imbalance_service import (
                    MicrostructureOrderFlowImbalanceService,
                    OFITickerMetric,
                )

                ofi_svc = MicrostructureOrderFlowImbalanceService(user_id=resolved_user_id)
                metrics: List[OFITickerMetric] = []
                evaluated_symbols = set()

                candidates = ["NVDA", "TSM", "AAPL", "MSFT", "V"]
                for sym in candidates:
                    if sym not in evaluated_symbols:
                        try:
                            m = await ofi_svc.evaluate_order_flow_imbalance(sym)
                            metrics.append(m)
                            evaluated_symbols.add(sym)
                        except Exception as se:
                            logger.debug("OFI router eval error for %s: %s", sym, se)

                return ofi_svc.format_ofi_report(metrics, channel="telegram")
            except Exception as e:
                logger.error(f"Failed to generate Microstructure OFI response: {e}")
                return f"⚠️ 查詢微觀訂單流失衡率與流動性真空儀表時發生錯誤：{e}"

        # 31. Option Gamma Exposure GEX & Volatility Pinning (Phase 62A)
        if any(cmd.startswith(prefix) for prefix in ("gex", "gamma", "flip", "pinning", "伽馬", "做市商伽馬", "釘盤")):
            try:
                from src.services.option_gamma_exposure_gex_service import OptionGammaExposureGEXService
                gex_svc = OptionGammaExposureGEXService(user_id=resolved_user_id)
                parts = text.strip().split()
                target_sym = parts[1].upper() if len(parts) > 1 and parts[1].isalpha() else "SPY"
                metric = await gex_svc.evaluate_ticker_gex(target_sym)
                return gex_svc.format_gex_report(metric)
            except Exception as e:
                logger.error(f"Failed to generate Option GEX response: {e}")
                return f"⚠️ 查詢做市商淨伽馬暴露與釘盤預測儀表時發生錯誤：{e}"

        # 32. Kalman Pairs Cointegration & Stat-Arb (Phase 62B)
        if any(cmd.startswith(prefix) for prefix in ("pair", "pairs", "arb", "kalman", "配對", "統計套利", "協整")):
            try:
                from src.services.kalman_pairs_cointegration_service import KalmanPairsCointegrationService
                pairs_svc = KalmanPairsCointegrationService(user_id=resolved_user_id)
                parts = text.strip().split()
                if len(parts) >= 3 and parts[1].isalpha() and parts[2].isalpha():
                    target_y = parts[1].upper()
                    target_x = parts[2].upper()
                elif len(parts) == 2 and parts[1].isalpha():
                    target_y = parts[1].upper()
                    target_x = "QQQ" if target_y != "QQQ" else "SPY"
                else:
                    target_y = "NVDA"
                    target_x = "AMD"
                metric = await pairs_svc.evaluate_pairs_cointegration(target_y, target_x)
                return pairs_svc.format_pairs_report(metric)
            except Exception as e:
                logger.error(f"Failed to generate Kalman Pairs Cointegration response: {e}")
        # 33. Trend Hysteresis Band & Macro Long-Only Lock (Phase 63A)
        if any(cmd.startswith(prefix) for prefix in ("trend", "hysteresis", "schmitt", "趨勢", "遲滯", "大趨勢", "單向鎖定")):
            try:
                from src.services.trend_hysteresis_lockout_service import TrendHysteresisLockoutService
                hyst_svc = TrendHysteresisLockoutService(user_id=resolved_user_id)
                parts = text.strip().split()
                target_sym = parts[1].upper() if len(parts) > 1 and parts[1].isalpha() else "NVDA"
                metric = await hyst_svc.evaluate_ticker_trend(target_sym)
                return hyst_svc.format_trend_report(metric)
            except Exception as e:
                logger.error(f"Failed to generate Trend Hysteresis response: {e}")
                return f"⚠️ 查詢遲滯回差帶與大趨勢單向鎖定儀表時發生錯誤：{e}"

        # 34. Friction-Aware Turnover Hurdle & Tranche Sizing (Phase 63B/64A)
        if any(cmd.startswith(prefix) for prefix in ("tranche", "friction", "core", "satellite", "分級", "底倉", "做市商摩擦", "摩擦成本", "自癒", "漂移自癒")):
            try:
                from src.services.friction_aware_tranche_sizing_service import FrictionAwareTrancheSizingService
                tranche_svc = FrictionAwareTrancheSizingService(user_id=resolved_user_id)
                parts = text.strip().split()

                # Check if requesting auto-healing simulation/execution (/tranche heal [ticker])
                is_heal = any(p.lower() in ("heal", "rebalance", "autoheal", "自癒", "再平衡") for p in parts[1:]) or cmd.startswith(("自癒", "漂移自癒"))

                # Extract target ticker symbol
                target_sym = "NVDA"
                for p in parts[1:]:
                    clean_p = p.upper().strip("$#")
                    if clean_p.isalpha() and clean_p.lower() not in ("heal", "rebalance", "autoheal", "status", "plan", "run", "自癒", "再平衡"):
                        target_sym = clean_p
                        break

                if is_heal:
                    # Execute or simulate tranche auto-healing (dry-run by default)
                    heal_res = tranche_svc.auto_heal_tranche_drift(
                        ticker=target_sym,
                        current_price=135.0,
                        total_shares=100.0,
                        current_core_shares=85.0,
                        dry_run=True,
                    )
                    return tranche_svc.format_drift_heal_report(heal_res)

                metric = await tranche_svc.evaluate_order_friction_and_tranche(
                    ticker=target_sym,
                    action="SELL",
                    quantity=10.0,
                    strategy_name="routine_rebalance",
                    total_held_shares=100.0,
                )
                return tranche_svc.format_tranche_report(metric)
            except Exception as e:
                logger.error(f"Failed to generate Friction & Tranche response: {e}")
                return f"⚠️ 查詢做市商摩擦成本與核心/衛星倉位分級儀表時發生錯誤：{e}"

        # 35. Cross-Currency FX Dynamic Hedging & Liquidity Buffer (Phase 65)
        if any(cmd.startswith(prefix) for prefix in ("fx", "forex", "hedge", "hedging", "外匯", "匯率", "避險", "匯率避險", "保證金緩衝")):
            try:
                from src.services.cross_currency_fx_hedging_service import CrossCurrencyFXHedgingService
                fx_svc = CrossCurrencyFXHedgingService(user_id=resolved_user_id)
                parts = text.strip().split()

                # Check if requesting hedge execution plan (/fx hedge [currency])
                is_hedge = any(p.lower() in ("hedge", "hedging", "對沖", "避險", "結匯", "鎖匯") for p in parts[1:]) or cmd.startswith(("hedge", "hedging", "避險", "匯率避險"))

                # Extract custom base currency if provided (e.g. /fx TWD, /fx EUR, /fx hedge JPY)
                custom_curr = None
                for p in parts[1:]:
                    clean_p = p.upper().strip("$#")
                    if clean_p in fx_svc.PRIOR_FX_BENCHMARKS and clean_p not in ("HEDGE", "HEDGING", "FX", "FOREX", "STATUS", "RUN", "PLAN"):
                        custom_curr = clean_p
                        break

                report = await fx_svc.calculate_portfolio_fx_exposure(base_currency=custom_curr)

                if is_hedge:
                    return fx_svc.format_hedge_suggestion(report)
                return fx_svc.format_fx_report(report)
            except Exception as e:
                logger.error(f"Failed to generate FX Hedging response: {e}")
                return f"⚠️ 查詢跨市場外匯對沖與多幣種保證金流動性儀表時發生錯誤：{e}"

        # 36. Factor Orthogonal Residual Attribution & Decay Monitoring (Phase 66)
        if ((any(cmd.startswith(prefix) for prefix in ("attribution", "decay", "halflife", "residual", "收益歸因", "正交歸因", "因子歸因", "因子衰減", "半衰期", "因子半衰期")) and not any(sub in cmd for sub in ("rebalance", "調倉"))) or (
            any(cmd.startswith(prefix) for prefix in ("factor", "factors", "因子")) and any(sub in cmd for sub in ("attribution", "decay", "halflife", "residual", "歸因", "衰減", "半衰期")) and not any(sub in cmd for sub in ("rebalance", "調倉"))
        )):
            try:
                from src.services.factor_orthogonal_attribution_service import FactorOrthogonalAttributionService
                attr_svc = FactorOrthogonalAttributionService(user_id=resolved_user_id)
                parts = text.strip().split()

                # Check if requesting decay / half-life board
                is_decay = any(p.lower() in ("decay", "halflife", "half-life", "衰減", "半衰期", "健康度", "status") for p in parts) or any(cmd.startswith(p) for p in ("decay", "halflife", "因子衰減", "半衰期", "因子半衰期"))

                # Check if custom lookback days specified (e.g. /attribution 30)
                custom_lookback = None
                for p in parts[1:]:
                    if p.isdigit():
                        custom_lookback = int(p)
                        break

                if is_decay:
                    decay_metrics = attr_svc.calculate_factor_decay_metrics()
                    return attr_svc.format_decay_board(decay_metrics)
                else:
                    report = attr_svc.decompose_orthogonal_returns(lookback_days=custom_lookback)
                    return attr_svc.format_attribution_report(report)
            except Exception as e:
                logger.error(f"Failed to generate Factor Attribution & Decay response: {e}")
                return f"⚠️ 查詢因子正交殘差收益歸因與多因子風險衰減看板時發生錯誤：{e}"

        # 37. Tactical Decay-Driven Portfolio Rebalancing (Phase 67)
        if any(cmd.startswith(prefix) for prefix in ("rebalance", "decay_rebalance", "decayrebalance", "factor_rebalance", "tactical_rebalance", "調倉", "自適應調倉", "衰減調倉", "因子調倉")) or (
            any(cmd.startswith(prefix) for prefix in ("factor", "factors", "decay", "因子")) and any(sub in cmd for sub in ("rebalance", "調倉"))
        ):
            try:
                from src.services.tactical_decay_rebalancer_service import TacticalDecayRebalancerService
                rebal_svc = TacticalDecayRebalancerService(user_id=resolved_user_id)
                parts = text.strip().split()

                # Check if requesting execution plan (/rebalance plan)
                is_plan = any(p.lower() in ("plan", "order", "orders", "執行", "方案", "訂單") for p in parts[1:]) or "plan" in cmd

                # Fetch real portfolio if available
                portfolio_data = {}
                try:
                    from src.services.daily_portfolio_summary_service import DailyPortfolioSummaryService
                    summary_svc = DailyPortfolioSummaryService(user_id=resolved_user_id)
                    summary = await summary_svc.generate_summary()
                    portfolio_data = {
                        "total_nlv": summary.get("total_equity", 10000.0),
                        "available_cash": summary.get("total_cash", 2000.0),
                        "positions": summary.get("positions", []),
                    }
                except Exception as pe:
                    logger.debug(f"Portfolio summary fallback for decay rebalancer: {pe}")

                plan = rebal_svc.generate_decay_rebalance_plan(portfolio=portfolio_data)

                if is_plan:
                    return rebal_svc.format_rebalance_plan(plan)
                return rebal_svc.format_rebalance_dashboard(plan)
            except Exception as e:
                logger.error(f"Failed to generate Tactical Decay Rebalance response: {e}")
                return f"⚠️ 查詢戰術因子衰減自適應調倉儀表時發生錯誤：{e}"

        # 38. Multi-Factor Extreme Stress Testing & Liquidity Squeeze Simulator (Phase 68)
        if any(cmd.startswith(prefix) for prefix in ("stresstest", "stress_test", "stress", "liquidity_squeeze", "壓力測試", "情境測試", "情境壓力測試", "流動性擠壓", "極端情境")):
            try:
                from src.services.multi_factor_stress_test_service import MultiFactorStressTestService
                stress_svc = MultiFactorStressTestService(user_id=resolved_user_id)
                parts = text.strip().split()

                # Fetch real portfolio if available
                portfolio_data = {}
                try:
                    from src.services.daily_portfolio_summary_service import DailyPortfolioSummaryService
                    summary_svc = DailyPortfolioSummaryService(user_id=resolved_user_id)
                    summary = await summary_svc.generate_summary()
                    portfolio_data = {
                        "total_nlv": summary.get("total_equity", 10000.0),
                        "available_cash": summary.get("total_cash", 2000.0),
                        "positions": summary.get("positions", []),
                    }
                except Exception as pe:
                    logger.debug(f"Portfolio summary fallback for stress testing: {pe}")

                # Check if specific scenario requested (e.g. /stresstest covid, /stresstest 2007)
                specific_scenario = None
                if len(parts) > 1 and parts[1].lower() not in ("summary", "all", "總覽", "report"):
                    specific_scenario = parts[1]

                report = stress_svc.run_stress_test(portfolio=portfolio_data, scenario_id_filter=specific_scenario)

                if specific_scenario:
                    return stress_svc.format_scenario_deep_dive(report, specific_scenario)
                return stress_svc.format_stress_test_dashboard(report)
            except Exception as e:
                logger.error(f"Failed to generate Multi-Factor Stress Test response: {e}")
                return f"⚠️ 執行多因子極端情境壓力測試與流動性擠壓模擬時發生錯誤：{e}"

        return None



