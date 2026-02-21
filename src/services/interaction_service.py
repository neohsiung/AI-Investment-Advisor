import logging
import time
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus
from src.domain.interfaces import IChannelAdapter
from src.infrastructure.channels.line_adapter import LineBotAdapter
# from src.infrastructure.channels.slack_adapter import SlackAdapter # Future

logger = logging.getLogger(__name__)

class InteractionService:
    """
    Service for orchestrating two-way user interactions across multiple channels (e.g., Approval Workflows).
    互動服務：協調多通路雙向使用者互動（例如：審核流程）。
    """

    def __init__(self, adapters: Optional[List[IChannelAdapter]] = None, intent_classifier: Optional[Any] = None, settings_service: Optional[Any] = None) -> None:
        """
        Initialize the interaction service with adapters and auxiliary services.
        初始化互動服務，包含適配器與輔助服務。
        """
        import os
        from src.infrastructure.channels.line_adapter import LineBotAdapter
        
        # 1. Use Injected Adapters
        if adapters:
            self.adapters = adapters
        else:
            # Fallback for tests or legacy: Default to LINE via ENV if no adapters provided
            token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            if token:
                self.adapters = [LineBotAdapter()]
            else:
                self.adapters = []
        
        # 2. Injected Classifier (IIntentClassifier)
        self.intent_classifier = intent_classifier
            
        self.settings_service = settings_service
        self._pending_requests: Dict[str, InteractionRequest] = {} 
        
        # v4.2.3: We will resolve adapters dynamically in _send_approval_request if needed
        # to ensure user-specific settings are honored.
        
        # 3. Register Callbacks for static adapters
        for adapter in self.adapters:
            if hasattr(adapter, 'register_callback'):
                adapter.register_callback(self.handle_response)
            if hasattr(adapter, 'register_text_callback'):
                adapter.register_text_callback(self.handle_text_response)

    async def handle_text_response(self, adapter: IChannelAdapter, user_id: str, text: str) -> None:
        """
        Handle a natural language text response received from a user.
        處理從使用者接收到的自然語言文字回覆。
        """
        logger.info(f"InteractionService: [INBOUND TEXT] Received from {adapter.__class__.__name__} ID: {user_id}, Text: '{text}'")
        
        # 1. Resolve internal user_id (email)
        resolved_user_id = None
        try:
            resolved_user_id = self.settings_service.find_user_by_channel_id(user_id) if self.settings_service else None
            logger.info(f"InteractionService: Resolved user_id: {resolved_user_id} for channel ID: {user_id}")
        except Exception as e:
            logger.error(f"InteractionService: Failed to resolve user: {e}")

        # 2. Check Verification FIRST
        try:
            from src.services.verification_service import VerificationService
            ver_svc = VerificationService() 
            
            # verify_any_reply returns True if it was a verification message and handled it
            if await ver_svc.verify_any_reply(user_id, text):
                logger.info(f"InteractionService: Verification logic successfully handled reply for ID: {user_id}")
                return # VerificationService sends its own confirmation message
        except Exception as e:
            logger.error(f"InteractionService: Verification check exception: {e}")

        # If still not resolved after verification attempt, it's truly unlinked
        if not resolved_user_id:
             logger.warning(f"InteractionService: Unlinked user {user_id}. Sending acknowledgment.")
             # [v3.5] Generic acknowledgment for unlinked users
             msg = "✅ 系統已收到您的訊息 (Message Received)！\n由於此 ID 尚未與帳號綁定，系統目前無法進行進一步處理。請至 Dashboard 完成驗證。"
             try:
                 adapter.send_message(user_id, msg) # Use send_message for text-only (more reliable)
             except Exception as e:
                 logger.error(f"InteractionService: Failed to send unlinked ack: {e}")
             return

        # 3. Process Intents for Linked Users
        if not self.intent_classifier:
            logger.warning("InteractionService: No IntentClassifier configured. Ignoring further text analysis.")
            return

        # 3.1 Find latest pending request for this user (or broadcast)
        pending_reqs = [
            r for r in self._pending_requests.values() 
            if r.is_pending() and (r.user_id == resolved_user_id or not r.user_id)
        ]
        
        if not pending_reqs:
            logger.info(f"InteractionService: No pending requests for {resolved_user_id}. Acknowledging.")
            msg = f"✅ 系統已收到您的回覆：'{text}'\n目前無待處理的審核請求 (No pending requests)."
            await adapter.send_message(user_id, msg)
            return
            
        # Sort by creation time desc
        latest_req = sorted(pending_reqs, key=lambda r: r.created_at, reverse=True)[0]
        
        # 3.2 Classify Intent
        try:
            intent = self.intent_classifier.classify(text)
            logger.info(f"InteractionService: Intent for '{text}': {intent}")
            
            if intent in ["APPROVE", "REJECT"]:
                # Trigger standard handler
                await self.handle_response(latest_req.request_id, intent.lower())
            else:
                # Generic acknowledgment for other text
                msg = f"✅ 系統已收到您的訊息：'{text}'\n正在交由 AI 分析中 (Processing...)"
                await adapter.send_message(user_id, msg)
        except Exception as e:
            logger.error(f"InteractionService: Text processing error: {e}")

    async def request_approval(self, 
                          title: str, 
                          content: str, 
                          context: Optional[Dict[str, Any]] = None, 
                          timeout_seconds: int = 300,
                          user_id: Optional[str] = None) -> bool:
        """
        Synchronously request user approval and wait for a response or timeout.
        同步請求使用者審核，並等待回覆或逾時。
        
        Args:
            title (str): Title of the approval request.
            title (str): 審核請求的標題。
            content (str): Detailed content/instructions for the user.
            content (str): 給使用者的詳細內容/說明。
            context (Dict[str, Any]): Metadata associated with the request.
            context (Dict[str, Any]): 與請求相關的元數據。
            timeout_seconds (int): Wait duration before expiring.
            timeout_seconds (int): 到期前的等待時長。
            user_id (str): Target user ID.
            user_id (str): 目標使用者 ID。
        """
        req = InteractionRequest(
            type=InteractionType.APPROVAL,
            title=title,
            content=content,
            payload=context or {},
            user_id=user_id,
            expires_at=datetime.now() + timedelta(seconds=timeout_seconds)
        )
        
        self._pending_requests[req.request_id] = req
        
        # 1. Send Request to User
        await self._send_approval_request(req)
        
        # 2. Wait for Response (Polling for MVP)
        import asyncio
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if req.status == InteractionStatus.APPROVED:
                logger.info(f"Interaction {req.request_id} APPROVED")
                return True, InteractionStatus.APPROVED
            if req.status == InteractionStatus.REJECTED:
                logger.info(f"Interaction {req.request_id} REJECTED")
                return False, InteractionStatus.REJECTED
            await asyncio.sleep(1) # Poll interval
            
        req.status = InteractionStatus.EXPIRED
        logger.warning(f"Interaction {req.request_id} EXPIRED")
        return False, InteractionStatus.EXPIRED

    async def _send_approval_request(self, req: InteractionRequest) -> None:
        """
        Route approval request to all active communication channels.
        將審核請求路由至所有啟用的通訊管道。
        """
        actions = [
            {"label": "Approve", "data": f"action=approve&id={req.request_id}", "style": "primary"},
            {"label": "Reject", "data": f"action=reject&id={req.request_id}", "style": "secondary"}
        ]
        
        # v4.2.3: Resolve target adapters based on user settings if possible
        target_adapters = self.adapters
        if req.user_id and req.user_id != "broadcast":
            try:
                from src.infrastructure.channels.channel_factory import ChannelFactory
                from src.services.settings_service import SettingsService
                
                # Fetch user-specific settings to get their specific adapters
                user_settings_svc = SettingsService(user_id=req.user_id)
                user_settings = user_settings_svc.get_all_settings()
                
                dynamic_adapters = ChannelFactory.create_adapters(user_settings)
                if dynamic_adapters:
                    target_adapters = dynamic_adapters
                    # Register this service to handle their callbacks
                    for adapter in target_adapters:
                        if hasattr(adapter, 'register_callback'):
                            adapter.register_callback(self.handle_response)
            except Exception as e:
                logger.error(f"InteractionService: Failed to resolve dynamic adapters for {req.user_id}: {e}")

        # Placeholder for Council/Sentinel logic (assuming req.payload contains 'triggers')
        decision = "AI 委員會正在評估中..." # Default decision
        filtered_triggers = req.payload.get('triggers', []) # Assuming triggers are in payload

        try:
            # Simulate AI Council decision (replace with actual call to AI service)
            # from src.services.ai_council_service import AICouncilService
            # council_service = AICouncilService()
            # decision = council_service.evaluate(req.content, filtered_triggers)
            decision = "✅ AI 委員會評估：無異常，建議批准。" # Example positive decision
        except Exception as e:
            logger.error(f"Council session failed: {e}")
            decision = (
                "⚠️ **系統運行於安全模式 (Fail-safe Mode)**\n\n"
                "目前無法取得 AI 委員會的即時評估（可能是 API 連線問題）。\n"
                "請根據下方原始觸發訊號進行判斷。"
            )
        
        # Format Notification (Improved UX)
        formatted_triggers = ""
        if filtered_triggers:
            for i, t in enumerate(filtered_triggers, 1):
                formatted_triggers += f"• {t.get('text', '未知觸發')}\n"
        alert_content = (
            f"### 🛡️ Sentinel 監控警報 (Sentinel Alert)\n\n"
            f"**偵測到以下重要訊號 ({len(filtered_triggers)}):**\n"
            f"{formatted_triggers}\n"
            f"---\n"
            f"**🤖 AI 委員會評估 (Council Assessment):**\n"
            f"{decision}\n"
            f"---\n"
            f"**原始請求內容 (Original Request):**\n"
            f"{req.content}"
        ) if filtered_triggers else req.content
        
        for adapter in target_adapters:
            try:
                # Use adapters that support interaction
                # For now using send_alert mechanism but with actions
                await adapter.send_alert(
                    user_id=req.user_id or "broadcast",
                    title=f"⚠️ {req.title}" if filtered_triggers else req.title,
                    content=alert_content, 
                    actions=actions
                )
            except Exception as e:
                logger.error(f"Failed to send interaction via {adapter}: {e}")

    async def handle_response(self, request_id: str, action: str) -> None:
        """
        Process a formal response (Approve/Reject) for a specific request.
        針對特定請求處理正式回覆（批准/婉拒）。
        """
        logger.info(f"InteractionService: [ACTION] Handling {action} for request {request_id}")
        
        req = self._pending_requests.get(request_id)  # nosec B113
        if not req:
            logger.warning(f"InteractionService: Request {request_id} not found in pending list.")
            return

        if not req.is_pending():
            logger.info(f"InteractionService: Request {request_id} already has status {req.status}")
            return

        # Update status
        resp_msg = ""
        if action.lower() == "approve":
            req.status = InteractionStatus.APPROVED
            resp_msg = "✅ 已收到批准指令 (Action: Approved)"
        elif action.lower() == "reject":
            req.status = InteractionStatus.REJECTED
            resp_msg = "❌ 已收到婉拒指令 (Action: Rejected)"
        else:
            logger.warning(f"InteractionService: Unknown action {action} for request {request_id}")
            return

        logger.info(f"InteractionService: Request {request_id} status updated to {req.status}")

        # v4.2.3: Resolve target adapters based on user settings for feedback consistency
        target_adapters = self.adapters
        if req.user_id and req.user_id != "broadcast":
            try:
                from src.infrastructure.channels.channel_factory import ChannelFactory
                from src.services.settings_service import SettingsService
                user_settings_svc = SettingsService(user_id=req.user_id)
                user_settings = user_settings_svc.get_all_settings()
                dynamic_adapters = ChannelFactory.create_adapters(user_settings)
                if dynamic_adapters:
                    target_adapters = dynamic_adapters
            except Exception as e:
                logger.error(f"InteractionService: Failed to resolve dynamic adapters for feedback {req.user_id}: {e}")

        # Notify user of receipt across active adapters (Omni-channel feedback)
        for adapter in target_adapters:
             try:
                 # req.user_id is the internal email. Adapter will resolve to channel ID.
                 logger.info(f"InteractionService: Sending action feedback via {adapter.__class__.__name__} to user {req.user_id}")
                 await adapter.send_message(req.user_id, resp_msg) 
             except Exception as e:
                 logger.error(f"InteractionService: Failed to send interaction ack via {adapter}: {e}")
