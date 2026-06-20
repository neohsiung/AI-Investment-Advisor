from src.utils.logger import setup_logger
logger = setup_logger("AutomatedTradingService")

import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime
import asyncio
import httpx
from src.repositories.settings_repository import AlchemySettingsRepository
from src.services.interaction_service import InteractionService
from src.services.notification_service import NotificationService
from src.domain.trading import Order, OrderAction, OrderType, OrderSizingMode
from src.services.broker_factory import BrokerFactory

class AutomatedTradingService:
    """
    Automated Trading Service.
    自動化交易服務。
    
    Handles the execution of trades based on AI confidence scores and user-defined thresholds.
    根據 AI 信心分數與使用者定義的閾值處理交易執行。
    """
    
    def __init__(self, settings_repo: Optional[AlchemySettingsRepository] = None, 
                 interaction_service: Optional[InteractionService] = None,
                 notification_service: Optional[NotificationService] = None):
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.interaction_service = interaction_service or InteractionService()
        self.notification_service = notification_service

    async def evaluate_and_execute_trade(self, user_id: str, ticker: str, action: str, quantity: float = None,
                                         confidence_score: int = None, rationale: str = None,
                                         target_weight: float = None, current_weight: float = None,
                                         delta_weight: float = None, portfolio_value: float = None,
                                         confidence_breakdown: list = None) -> Dict[str, Any]:
        """
        Evaluate and potentially execute a trade based on confidence score.
        評估並可能根據信心分數執行交易。
        
        v7.0: Support weight-based position sizing (fractional shares)
        - If target_weight/current_weight/delta_weight provided: calculate quantity from weights
        - Otherwise: use legacy quantity-based approach
        """
        
        # v4.2.2: Ensure notification service is correctly configured for this user
        if not self.notification_service:
            from src.services.settings_service import SettingsService
            from src.services.notification_service import NotificationService
            settings_svc = SettingsService(user_id=user_id)
            self.notification_service = NotificationService.create_with_settings(settings_service=settings_svc, user_id=user_id)

        # [NEW v7.0] Weight-based quantity calculation
        # If target_weight is provided, calculate quantity from delta_weight
        if delta_weight is not None and portfolio_value is not None and quantity is None:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    # Get current price for the ticker
                    # Note: This is a simplified approach; actual implementation may need more sophisticated pricing
                    current_price = await self._get_current_price(broker, ticker)
                    if current_price and current_price > 0:
                        # Calculate dollar amount from delta_weight
                        delta_amount = delta_weight * portfolio_value
                        quantity = delta_amount / current_price
                        logger.info(f"Weight-based calculation: delta_weight={delta_weight}, portfolio_value=${portfolio_value}, current_price=${current_price}, quantity={quantity:.4f}")
                    else:
                        logger.warning(f"Could not get current price for {ticker}, falling back to legacy approach")
                        if quantity is None:
                            quantity = 1.0  # Default fallback
            except Exception as e:
                logger.warning(f"Weight-based calculation failed: {e}, using quantity parameter")
                if quantity is None:
                    quantity = 1.0  # Default fallback
        
        # Ensure quantity is set
        if quantity is None:
            quantity = 1.0

        # 1. Check if trading is enabled
        trading_enabled = self.settings_repo.get(user_id, "ai_trading_enabled")
        if trading_enabled is not None and str(trading_enabled).lower() != "true":
            logger.warning(f"Trade Execution Blocked: AI Trading is disabled for user {user_id}")
            return {"status": "blocked", "reason": "Trading is disabled in settings"}
        
        # 2. Get the thresholds (upper + lower bound)
        raw_threshold = self.settings_repo.get(user_id, "auto_trade_threshold")
        threshold = int(raw_threshold) if raw_threshold is not None else 9
        
        # v8.2: Enhanced Excess Cash Detection with multiple trigger patterns
        # 增強現金過高檢測，支援多種觸發模式
        is_excess_cash = (
            "現金比例過高" in rationale or 
            "現金水位過高" in rationale or
            "現金水位明顯過高" in rationale or
            "現金再投資" in rationale or
            "Excess Cash" in rationale or 
            "High Cash" in rationale or
            "cash_ratio >" in rationale  # Quantitative pattern
        )
        if is_excess_cash:
            reinvest_threshold = int(self.settings_repo.get(user_id, "auto_reinvest_threshold") or 7)
            if threshold > reinvest_threshold:
                logger.info(f"Excess Cash Reinvestment: Lowering threshold {threshold} -> {reinvest_threshold} for {ticker}")
                threshold = reinvest_threshold
        
        raw_min_threshold = self.settings_repo.get(user_id, "auto_trade_min_threshold")
        min_threshold = int(raw_min_threshold) if raw_min_threshold is not None else 3
        
        # ── Normalize confidence to 0-10 scale for consistent comparison ──
        # Sentinel passes 0-100 (e.g. 86) but thresholds are 0-10 (e.g. 7)
        # RebalanceService passes 0-10 (e.g. 8) — leave as-is.
        if confidence_score is not None and confidence_score > 10:
            normalized_confidence = round(confidence_score / 10)
        else:
            normalized_confidence = confidence_score
        
        logger.info(
            f"evaluating trade for {ticker}. Score: {normalized_confidence} (raw={confidence_score}), "
            f"Min: {min_threshold}, Threshold: {threshold} (ExcessCash={is_excess_cash})"
        )
        
        # 3. Decision Logic (三段式閥值)
        # 3a. Below minimum → skip silently, no notification
        if normalized_confidence < min_threshold:
            logger.info(
                f"Score {normalized_confidence} < min_threshold {min_threshold}. "
                f"Skipping silently for {ticker}."
            )
            return {"status": "skipped", "reason": f"Score {normalized_confidence} below minimum threshold {min_threshold}"}
        
        # Prepare Order object
        order_action = OrderAction.BUY if action.upper() == "BUY" else OrderAction.SELL
        
        # v6.0: Position Sizing Guard (現金水位與持倉比例守衛)
        # ─────────────────────────────────────────────────
        if order_action == OrderAction.BUY:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    account = await broker.get_account()
                    if account and account.total_equity > 0:
                        nlv = account.total_equity
                        cash = account.available_cash
                        
                        # Dynamic settings (Rule #8: no hardcoded thresholds)
                        max_pct = float(self.settings_repo.get(user_id, "max_single_position_pct") or 0.10)
                        min_amount = float(self.settings_repo.get(user_id, "min_trade_amount") or 10.0)
                        
                        max_amount = nlv * max_pct
                        original_qty = quantity
                        
                        # Clamp to available cash
                        if quantity > cash:
                            logger.warning(f"Position Sizing: Clamped ${quantity:.2f} → ${cash:.2f} (available cash)")
                            quantity = cash
                        
                        # Clamp to max position percentage
                        if quantity > max_amount:
                            logger.warning(f"Position Sizing: Clamped ${quantity:.2f} → ${max_amount:.2f} ({max_pct*100:.0f}% of NLV ${nlv:.2f})")
                            quantity = max_amount
                        
                        # Check minimum
                        if quantity < min_amount:
                            logger.info(f"Position Sizing: Amount ${quantity:.2f} below minimum ${min_amount:.2f}. Skipping.")
                            return {"status": "skipped", "reason": f"Amount ${quantity:.2f} below minimum (${min_amount:.2f})"}
                        
                        if quantity != original_qty:
                            logger.info(f"Position Sizing: Adjusted {ticker} amount ${original_qty:.2f} → ${quantity:.2f} (NLV: ${nlv:.2f}, Cash: ${cash:.2f})")
                        
                        # Phase 2: Explicit rounding for USD amount
                        quantity = round(quantity, 2)
            except Exception as e:
                logger.warning(f"Position Sizing check failed (non-blocking): {e}")
        
        # v7.0: SELL Position Sizing Guard (持倉守衛 — 最後防線)
        # ─────────────────────────────────────────────────
        if order_action == OrderAction.SELL:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    positions = await broker.get_positions()  # ← async
                    actual_holding = 0.0
                    for p in positions:
                        p_sym = str(getattr(p, 'symbol', '')).strip().upper()
                        t_sym = ticker.strip().upper()
                        
                        # Handle unresolved ID_xxxx symbols
                        if p_sym.startswith("ID_"):
                            # Check if the broker can resolve it
                            resolved = None
                            if hasattr(broker, '_resolve_id_to_symbol'):
                                resolved = broker._resolve_id_to_symbol(p_sym[3:])
                            
                            if resolved:
                                p_sym = resolved.strip().upper()
                            else:
                                # If it's still ID_xxxx, we can't match it unless we know the ticker's ID
                                # For now, skip and log
                                logger.debug(f"SELL Guard: Skipping unresolved position {p_sym}")
                                continue

                        # Normalize eToro suffixes
                        for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                            if p_sym.endswith(suffix):
                                p_sym = p_sym[:-len(suffix)]
                        if p_sym == t_sym:
                            actual_holding += getattr(p, 'quantity', 0)
                    
                    original_qty = quantity
                    
                    if actual_holding <= 0:
                        logger.info(f"SELL Guard: No active position for {ticker}. Skipping trade.")
                        return {"status": "skipped", "reason": f"No active position for {ticker}"}
                    
                    if quantity > actual_holding:
                        logger.warning(f"SELL Guard: Clamped {ticker} from {quantity} → {actual_holding} (actual holding)")
                        quantity = actual_holding
                    
                    if quantity != original_qty:
                        logger.info(f"SELL Guard: Adjusted {ticker} qty {original_qty} → {quantity} (holding: {actual_holding})")
                    
                    # Phase 2: Explicit rounding for eToro 0.01 share precision
                    quantity = round(quantity, 2)
            except Exception as e:
                logger.warning(f"SELL Position Sizing check failed (non-blocking): {e}")
        
        order = Order(
            symbol=ticker,
            action=order_action,
            quantity=quantity,
            amount_usd=quantity if order_action == OrderAction.BUY else None,
            sizing_mode=OrderSizingMode.AMOUNT if order_action == OrderAction.BUY else OrderSizingMode.SHARES,
            order_type=OrderType.MARKET,
            reason=rationale
        )
        
        # 3b. Above upper threshold → auto-execute
        if normalized_confidence >= threshold:
            logger.info(f"Score {normalized_confidence} >= {threshold}. Executing automatically.")
            return await self._execute_trade(user_id, order, normalized_confidence, rationale, "✅ [自動執行] (Auto-Approved)", confidence_breakdown=confidence_breakdown)
        
        # 3c. Between min and upper → notify all channels, request approval
        logger.info(f"Score {normalized_confidence} in [{min_threshold}, {threshold}). Requesting approval.")
        return await self._request_approval_and_execute(user_id, order, normalized_confidence, rationale, confidence_breakdown=confidence_breakdown)

    async def _request_approval_and_execute(self, user_id: str, order: Order, confidence_score: int, rationale: str, confidence_breakdown: list = None) -> Dict[str, Any]:
        """Request user approval synchronously via InteractionService."""
        
        # Build breakdown display
        breakdown_lines = []
        if confidence_breakdown and len(confidence_breakdown) > 0:
            breakdown_lines.append("📊 Confidence Breakdown:")
            for sub in confidence_breakdown:
                agent = sub.get("agent", "?")
                score = sub.get("confidence", 0)
                factor = sub.get("key_factor", "")
                breakdown_lines.append(f"  ├─ {agent}: {score}/10 ({factor})")
        breakdown_str = "\n".join(breakdown_lines) + "\n" if breakdown_lines else ""
        
        title = f"🛎️ [需要核准] 交易請求 (Trade Approval Required) - {order.symbol}"
        content = (
            f"**AI 建議執行交易 (AI Trade Recommendation)**\n\n"
            f"• **標的 (Ticker)**: {order.symbol}\n"
            f"• **方向 (Action)**: {order.action.value}\n"
            f"• **數量 (Quantity)**: {order.quantity}\n"
            f"• **AI 把握度 (Confidence)**: **{confidence_score}/10**\n"
            f"{breakdown_str}"
            f"**💡 AI 評分理由 (Rationale)**:\n"
            f"{rationale}\n\n"
            f"⚠️ *請在 5 分鐘內做出決定，逾期將自動失效。*"
        )
        
        # Request approval (Timeout 300 seconds = 5 mins)
        logger.info(f"Requesting approval from user {user_id} for {order.symbol}")
        
        try:
            # v4.2.3: Handle detailed status results (Approved/Rejected/Expired)
            is_approved, status = await self.interaction_service.request_approval(
                user_id=user_id,
                title=title,
                content=content,
                timeout_seconds=300 
            )
            
            if is_approved:
                logger.info(f"User {user_id} approved trade for {order.symbol}")
                return await self._execute_trade(user_id, order, confidence_score, rationale, "👤 [核准執行] (User-Approved)", confidence_breakdown=confidence_breakdown)
            else:
                from src.domain.interaction import InteractionStatus
                if status == InteractionStatus.EXPIRED:
                    logger.warning(f"Trade approval for {order.symbol} EXPIRED after 5 mins.")
                    notif_title = f"❌ [交易失效] 逾時未處理 - {order.symbol}"
                    notif_content = f"審核請求已逾時過期 (Approval Request Expired)。\n\n**標的:** {order.symbol}\n**方向:** {order.action.value}\n**原因:** 5 分鐘內未收到回應。"
                else:
                    logger.info(f"User {user_id} rejected trade for {order.symbol}")
                    notif_title = f"❌ [交易取消] 使用者拒絕 - {order.symbol}"
                    notif_content = f"使用者已拒絕此項交易 (User Rejected)。\n\n**標的:** {order.symbol}\n**方向:** {order.action.value}"

                await self._notify_via_api(
                    user_id=user_id,
                    title=notif_title,
                    content=notif_content,
                    category="approval"
                )
                return {"status": "rejected_or_timeout", "reason": f"Trade {status.name if hasattr(status, 'name') else status}"}
                
        except Exception as e:
            logger.error(f"Approval workflow failed: {e}")
            return {"status": "error", "reason": f"Approval workflow failed: {e}"}

    async def _execute_trade(self, user_id: str, order: Order, confidence_score: int, rationale: str, approval_type: str, confidence_breakdown: list = None) -> Dict[str, Any]:
        """Execute the trade via the BrokerFactory."""
        
        broker = BrokerFactory.get_broker(user_id)
        if not broker:
            msg = "Broker validation failed: No preferred broker configured."
            logger.error(msg)
            return {"status": "failed", "reason": msg}
            
        logger.info(f"Executing {order.action.value} {order.symbol} via {broker.get_name()}")
        
        try:
            # Order execution is synchronous in current design
            result = await broker.execute_order(order)  # ← async
            
            # v6.0: Post-Trade Sync (交易後紀錄同步)
            if result.get("status") not in ["failed", "error"] and not result.get("error"):
                try:
                    await broker.sync_history(user_id)  # ← async
                    logger.info("Post-trade sync completed.")
                except Exception as sync_e:
                    logger.warning(f"Post-trade sync failed (non-blocking): {sync_e}")
            
            # Send Notification
            title = f"✅ 交易執行成功 (Trade Executed) - {order.symbol}"
            if result.get("status") in ["failed", "error"]:
                 title = f"⚠️ 交易執行失敗 (Trade Failed) - {order.symbol}"
            
            content = (
                f"**券商 (Broker)**: {broker.get_name()}\n"
                f"**標的 (Ticker)**: {order.symbol}\n"
                f"**方向 (Action)**: {order.action.value}\n"
                f"**數量 (Quantity)**: {order.quantity}\n"
                f"**執行方式 (Type)**: {approval_type}\n"
                f"**把握度 (Confidence)**: {confidence_score}/10\n\n"
        + (
            "\n".join([
                "📊 Confidence Breakdown:",
                *[f"  ├─ {s['agent']}: {s['confidence']}/10 ({s.get('key_factor', '-')})"
                  for s in (confidence_breakdown or [])[:3]]
            ]) + "\n\n"
            if confidence_breakdown
            else ""
        )
        + 
                f"**💡 AI 評分理由 (Rationale)**:\n{rationale}\n\n"
                f"**詳細結果 (Details)**: `{result}`"
            )
            
            await self._notify_via_api(
                user_id=user_id, 
                title=title, 
                content=content,
                category="approval"
            )
            
            return result
        except Exception as e:
             logger.error(f"Trade execution failed: {e}")
             return {"status": "error", "reason": str(e)}

    async def _get_current_price(self, broker, ticker: str) -> float:
        """Get current price for a ticker from broker."""
        try:
            # Try to get from market data if available
            if hasattr(broker, 'get_quote'):
                quote = await broker.get_quote(ticker)
                if quote and 'price' in quote:
                    return float(quote['price'])
            
            # Fallback: try to get from positions or market data
            logger.warning(f"Could not retrieve price for {ticker} from broker")
            return None
        except Exception as e:
            logger.warning(f"Error getting price for {ticker}: {e}")
            return None


    async def _notify_via_api(
        self, user_id: str, title: str, content: str, category: str = "approval"
    ) -> None:
        """
        Dispatch notification via direct NotificationService.
        透過直接 NotificationService 發送通知，繞過已失效的通知微服務。
        """
        try:
            if not self.notification_service:
                from src.services.settings_service import SettingsService
                from src.services.notification_service import NotificationService
                settings_svc = SettingsService(user_id=user_id)
                self.notification_service = NotificationService.create_with_settings(
                    settings_service=settings_svc, user_id=user_id
                )
            
            # [T2] Get user's preferred channels (no hardcoding §5.2)
            from src.services.notification_settings_manager import NotificationSettingsManager
            from src.repositories.settings_repository import AlchemySettingsRepository
            nsm = NotificationSettingsManager(
                settings_repo=AlchemySettingsRepository(), 
                user_id=user_id
            )
            user_channels = nsm.get_active_notification_channels()
            if not user_channels:
                user_channels = ["web", "telegram"] # Fallback

            await self.notification_service.notify_all(
                title=title,
                content=content,
                user_id=user_id,
                channels=user_channels,
                category=category
            )
            logger.info(f"Trade notification dispatched via direct NotificationService for {user_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch trade notification: {e}")

    async def process_council_decision(self, user_id: str, decision_text: str) -> List[Dict[str, Any]]:
        """
        Extract trade recommendations from Council decisions and execute them based on confidence.
        從評議會決策中提取交易建議，並根據信心分數執行。
        """
        from src.agents.skills.skill_loader import SkillLoader
        import json
        
        logger.info(f"AutomatedTradingService: Extracting actions from Council decision for user {user_id}")
        loader = SkillLoader(user_id=user_id)
        
        # Skillified: Use extract_actions skill instead of dedicated agent
        trades_json = await loader.run_skill("extract_actions", user_id=user_id, decision_text=decision_text)
        trades = json.loads(trades_json)

        if not trades:
            logger.info("AutomatedTradingService: No actionable trades found in Council decision.")
            return []
            
        results = []
        for trade in trades:
            ticker = trade.get("ticker")
            action = trade.get("action")
            confidence = int(trade.get("confidence", 5))
            reason = trade.get("reason", "Council Recommendation")
            
            # v7.0: Support both legacy (quantity) and new (weight-based) formats
            quantity = None
            target_weight = None
            current_weight = None
            delta_weight = None
            portfolio_value = None
            
            # Try weight-based format first
            if "target_weight" in trade and "delta_weight" in trade:
                target_weight = float(trade.get("target_weight"))
                current_weight = float(trade.get("current_weight", 0))
                delta_weight = float(trade.get("delta_weight"))
                portfolio_value = float(trade.get("portfolio_value", 0))
                logger.info(f"AutomatedTradingService: Extracted weight-based trade -> {action} {ticker} (target_weight={target_weight}%, delta={delta_weight:+.2%}, Confidence: {confidence})")
            else:
                # Legacy format: use quantity
                quantity = float(trade.get("quantity", 1.0))
                logger.info(f"AutomatedTradingService: Extracted legacy trade -> {action} {quantity} {ticker} (Confidence: {confidence})")
            
            if ticker and action:
                res = await self.evaluate_and_execute_trade(
                    user_id=user_id, 
                    ticker=ticker, 
                    action=action, 
                    quantity=quantity,
                    confidence_score=confidence, 
                    rationale=reason,
                    target_weight=target_weight,
                    current_weight=current_weight,
                    delta_weight=delta_weight,
                    portfolio_value=portfolio_value
                )
                results.append(res)
            else:
                logger.warning(f"AutomatedTradingService: Missing required fields in extracted trade: {trade}")
                
        return results
