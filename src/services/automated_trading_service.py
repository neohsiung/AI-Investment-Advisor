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
from src.domain.trading import Order, OrderAction, OrderType
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
        self.notification_api_url = os.getenv("NOTIFICATION_API_URL", "http://notification:8001/api/v1/notify")

    async def evaluate_and_execute_trade(self, user_id: str, ticker: str, action: str, quantity: float, 
                                         confidence_score: int, rationale: str) -> Dict[str, Any]:
        """
        Evaluate and potentially execute a trade based on confidence score.
        評估並可能根據信心分數執行交易。
        """
        
        # v4.2.2: Ensure notification service is correctly configured for this user
        if not self.notification_service:
            from src.services.settings_service import SettingsService
            from src.services.notification_service import NotificationService
            settings_svc = SettingsService(user_id=user_id)
            self.notification_service = NotificationService.create_with_settings(settings_service=settings_svc, user_id=user_id)

        # 1. Check if trading is enabled
        trading_enabled = self.settings_repo.get(user_id, "ai_trading_enabled")
        if trading_enabled is not None and str(trading_enabled).lower() != "true":
            logger.warning(f"Trade Execution Blocked: AI Trading is disabled for user {user_id}")
            return {"status": "blocked", "reason": "Trading is disabled in settings"}
        
        # 2. Get the thresholds (upper + lower bound)
        raw_threshold = self.settings_repo.get(user_id, "auto_trade_threshold")
        threshold = int(raw_threshold) if raw_threshold is not None else 9
        
        raw_min_threshold = self.settings_repo.get(user_id, "auto_trade_min_threshold")
        min_threshold = int(raw_min_threshold) if raw_min_threshold is not None else 3
        
        logger.info(
            f"evaluating trade for {ticker}. Score: {confidence_score}, "
            f"Min: {min_threshold}, Threshold: {threshold}"
        )
        
        # 3. Decision Logic (三段式閥值)
        # 3a. Below minimum → skip silently, no notification
        if confidence_score < min_threshold:
            logger.info(
                f"Score {confidence_score} < min_threshold {min_threshold}. "
                f"Skipping silently for {ticker}."
            )
            return {"status": "skipped", "reason": f"Score {confidence_score} below minimum threshold {min_threshold}"}
        
        # Prepare Order object
        order_action = OrderAction.BUY if action.upper() == "BUY" else OrderAction.SELL
        
        # v6.0: Position Sizing Guard (現金水位與持倉比例守衛)
        # ─────────────────────────────────────────────────
        if order_action == OrderAction.BUY:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    account = broker.get_account()
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
            except Exception as e:
                logger.warning(f"Position Sizing check failed (non-blocking): {e}")
        
        order = Order(
            symbol=ticker,
            action=order_action,
            quantity=quantity,
            order_type=OrderType.MARKET,
            reason=rationale
        )
        
        # 3b. Above upper threshold → auto-execute
        if confidence_score >= threshold:
            logger.info(f"Score {confidence_score} >= {threshold}. Executing automatically.")
            return await self._execute_trade(user_id, order, confidence_score, rationale, "✅ [自動執行] (Auto-Approved)")
        
        # 3c. Between min and upper → notify all channels, request approval
        logger.info(f"Score {confidence_score} in [{min_threshold}, {threshold}). Requesting approval.")
        return await self._request_approval_and_execute(user_id, order, confidence_score, rationale)

    async def _request_approval_and_execute(self, user_id: str, order: Order, confidence_score: int, rationale: str) -> Dict[str, Any]:
        """Request user approval synchronously via InteractionService."""
        
        title = f"🛎️ [需要核准] 交易請求 (Trade Approval Required) - {order.symbol}"
        content = (
            f"**AI 建議執行交易 (AI Trade Recommendation)**\n\n"
            f"• **標的 (Ticker)**: {order.symbol}\n"
            f"• **方向 (Action)**: {order.action.value}\n"
            f"• **數量 (Quantity)**: {order.quantity}\n"
            f"• **AI 把握度 (Confidence)**: **{confidence_score}/10**\n\n"
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
                return await self._execute_trade(user_id, order, confidence_score, rationale, "👤 [核准執行] (User-Approved)")
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

    async def _execute_trade(self, user_id: str, order: Order, confidence_score: int, rationale: str, approval_type: str) -> Dict[str, Any]:
        """Execute the trade via the BrokerFactory."""
        
        broker = BrokerFactory.get_broker(user_id)
        if not broker:
            msg = "Broker validation failed: No preferred broker configured."
            logger.error(msg)
            return {"status": "failed", "reason": msg}
            
        logger.info(f"Executing {order.action.value} {order.symbol} via {broker.get_name()}")
        
        try:
            # Order execution is synchronous in current design
            result = broker.execute_order(order)
            
            # v6.0: Post-Trade Sync (交易後紀錄同步)
            if result.get("status") not in ["failed", "error"] and not result.get("error"):
                try:
                    broker.sync_history(user_id)
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

    async def _notify_via_api(
        self, user_id: str, title: str, content: str, category: str = "approval"
    ) -> None:
        """
        Dispatch notification via standalone Notification Microservice HTTP API.
        透過獨立通知微服務 HTTP API 發送通知，確保所有啟用管道（含 LINE）都能收到。
        """
        payload = {
            "user_id": user_id,
            "title": title,
            "content": content,
            "channels": ["line", "telegram", "email", "discord", "slack"],
            "category": category
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notification_api_url, json=payload, timeout=5.0
                )
                if response.status_code == 202:
                    logger.info(f"Trade notification dispatched for {user_id}")
                else:
                    logger.warning(
                        f"Notification API returned {response.status_code}: {response.text}"
                    )
        except Exception as e:
            logger.error(f"Failed to dispatch trade notification via API: {e}")
    async def process_council_decision(self, user_id: str, decision_text: str) -> List[Dict[str, Any]]:
        """
        Extract trade recommendations from Council decisions and execute them based on confidence.
        從評議會決策中提取交易建議，並根據信心分數執行。
        """
        from src.agents.factory import AgentFactory
        
        logger.info(f"AutomatedTradingService: Extracting actions from Council decision for user {user_id}")
        extractor = AgentFactory.create_action_extractor_agent(user_id=user_id, tier="fast")
        
        trades = extractor.run(decision_text)
        if not trades:
            logger.info("AutomatedTradingService: No actionable trades found in Council decision.")
            return []
            
        results = []
        for trade in trades:
            ticker = trade.get("ticker")
            action = trade.get("action")
            quantity = float(trade.get("quantity", 1.0))
            confidence = int(trade.get("confidence", 5))
            reason = trade.get("reason", "Council Recommendation")
            
            if ticker and action:
                logger.info(f"AutomatedTradingService: Extracted trade -> {action} {quantity} {ticker} (Confidence: {confidence})")
                res = await self.evaluate_and_execute_trade(
                    user_id=user_id, 
                    ticker=ticker, 
                    action=action, 
                    quantity=quantity, 
                    confidence_score=confidence, 
                    rationale=reason
                )
                results.append(res)
            else:
                logger.warning(f"AutomatedTradingService: Missing required fields in extracted trade: {trade}")
                
        return results
