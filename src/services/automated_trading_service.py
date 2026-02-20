import logging
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio

from src.domain.trading import Order, OrderAction, OrderType
from src.services.broker_factory import BrokerFactory
from src.services.interaction_service import InteractionService
from src.repositories.settings_repository import AlchemySettingsRepository
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

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
        self.notification_service = notification_service or NotificationService()

    async def evaluate_and_execute_trade(self, user_id: str, ticker: str, action: str, quantity: float, 
                                         confidence_score: int, rationale: str) -> Dict[str, Any]:
        """
        Evaluate and potentially execute a trade based on confidence score.
        評估並可能根據信心分數執行交易。
        """
        
        # 1. Check if trading is enabled
        trading_enabled = self.settings_repo.get(user_id, "ai_trading_enabled")
        if trading_enabled is not None and str(trading_enabled).lower() != "true":
            logger.warning(f"Trade Execution Blocked: AI Trading is disabled for user {user_id}")
            return {"status": "blocked", "reason": "Trading is disabled in settings"}
        
        # 2. Get the threshold
        raw_threshold = self.settings_repo.get(user_id, "auto_trade_threshold")
        threshold = int(raw_threshold) if raw_threshold is not None else 9
        
        logger.info(f"evaluating trade for {ticker}. Score: {confidence_score}, Threshold: {threshold}")
        
        # Prepare Order object
        order_action = OrderAction.BUY if action.upper() == "BUY" else OrderAction.SELL
        order = Order(
            symbol=ticker,
            action=order_action,
            quantity=quantity,
            order_type=OrderType.MARKET,
            reason=rationale
        )
        
        # 3. Decision Logic
        if confidence_score >= threshold:
            logger.info(f"Score {confidence_score} >= {threshold}. Executing automatically.")
            return await self._execute_trade(user_id, order, confidence_score, rationale, "Auto-Approved")
        else:
            logger.info(f"Score {confidence_score} < {threshold}. Requesting approval.")
            return await self._request_approval_and_execute(user_id, order, confidence_score, rationale)

    async def _request_approval_and_execute(self, user_id: str, order: Order, confidence_score: int, rationale: str) -> Dict[str, Any]:
        """Request user approval synchronously via InteractionService."""
        
        title = f"🛎️ 交易批准請求 (Trade Approval Request) - {order.symbol}"
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
            is_approved = await self.interaction_service.request_approval(
                user_id=user_id,
                title=title,
                content=content,
                timeout_seconds=300 
            )
            
            if is_approved:
                logger.info(f"User {user_id} approved trade for {order.symbol}")
                return await self._execute_trade(user_id, order, confidence_score, rationale, "User-Approved")
            else:
                logger.info(f"User {user_id} rejected or timed out trade for {order.symbol}")
                # Notify rejection/timeout
                await self.notification_service.send_alert(
                    user_id=user_id,
                    title=f"❌ 交易取消 (Trade Cancelled) - {order.symbol}",
                    content=f"使用者拒絕或已逾時 (Rejected or Timed Out)。\n\n**標的:** {order.symbol}\n**方向:** {order.action.value}"
                )
                return {"status": "rejected_or_timeout", "reason": "User rejected or request expired"}
                
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
            
            await self.notification_service.send_alert(user_id=user_id, title=title, content=content)
            
            return result
        except Exception as e:
             logger.error(f"Trade execution failed: {e}")
             return {"status": "error", "reason": str(e)}
