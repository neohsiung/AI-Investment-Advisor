from src.utils.logger import setup_logger
logger = setup_logger("InteractionService")

import time
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime, timedelta

from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus
from src.domain.interfaces import IChannelAdapter
from src.infrastructure.channels.line_adapter import LineBotAdapter
from src.services.conversation_router import ConversationRouter

def serialize_request(req: InteractionRequest) -> str:
    import json
    return json.dumps({
        "request_id": req.request_id,
        "type": req.type.value,
        "title": req.title,
        "content": req.content,
        "payload": req.payload,
        "status": req.status.value,
        "response": req.response,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "channel_id": req.channel_id,
        "user_id": req.user_id
    })

def deserialize_request(data_str: str) -> InteractionRequest:
    import json
    from datetime import datetime
    from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus
    data = json.loads(data_str)
    
    created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
    expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
    
    return InteractionRequest(
        request_id=data["request_id"],
        type=InteractionType(data["type"]),
        title=data["title"],
        content=data["content"],
        payload=data["payload"],
        status=InteractionStatus(data["status"]),
        response=data["response"],
        created_at=created_at,
        expires_at=expires_at,
        channel_id=data.get("channel_id"),
        user_id=data.get("user_id")
    )

class RedisPendingRequests:
    def __init__(self):
        import os
        import sys
        import redis
        self._fallback_dict = {}
        
        # Check if we are running in a unit test environment
        is_testing = "pytest" in sys.modules or os.getenv("TESTING") == "true"
        
        if is_testing:
            self._redis = None
        else:
            try:
                from src.infrastructure.cache.redis_client import get_redis_sync
                self._redis = get_redis_sync()
                self._redis.ping()
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None

    def __setitem__(self, key: str, req: InteractionRequest):
        self._fallback_dict[key] = req
        if self._redis:
            try:
                self._redis.set(f"interaction:{key}", serialize_request(req), ex=3600)  # TTL of 1 hour
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None

    def __getitem__(self, key: str) -> InteractionRequest:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __delitem__(self, key: str):
        if self._redis:
            try:
                self._redis.delete(f"interaction:{key}")
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        if key in self._fallback_dict:
            del self._fallback_dict[key]

    def __len__(self) -> int:
        if self._redis:
            try:
                return len(self._redis.keys("interaction:*"))
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        return len(self._fallback_dict)

    def __contains__(self, key: str) -> bool:
        if self._redis:
            try:
                return bool(self._redis.exists(f"interaction:{key}"))
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        return key in self._fallback_dict

    def get(self, key: str, default=None) -> Optional[InteractionRequest]:
        if self._redis:
            try:
                val = self._redis.get(f"interaction:{key}")
                if val:
                    redis_req = deserialize_request(val)
                    if key in self._fallback_dict:
                        local_req = self._fallback_dict[key]
                        local_req.status = redis_req.status
                        local_req.response = redis_req.response
                        return local_req
                    return redis_req
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        return self._fallback_dict.get(key, default)

    def pop(self, key: str, default=None) -> Optional[InteractionRequest]:
        val = self.get(key)
        if val is not None:
            self.__delitem__(key)
            return val
        return default

    def keys(self) -> List[str]:
        if self._redis:
            try:
                raw_keys = self._redis.keys("interaction:*")
                return [k.replace("interaction:", "") for k in raw_keys]
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        return list(self._fallback_dict.keys())

    def values(self) -> List[InteractionRequest]:
        reqs = []
        if self._redis:
            try:
                keys = self._redis.keys("interaction:*")
                for k in keys:
                    val = self._redis.get(k)
                    if val:
                        # Apply same local reference mapping to values() as well
                        redis_req = deserialize_request(val)
                        req_id = redis_req.request_id
                        if req_id in self._fallback_dict:
                            local_req = self._fallback_dict[req_id]
                            local_req.status = redis_req.status
                            local_req.response = redis_req.response
                            reqs.append(local_req)
                        else:
                            reqs.append(redis_req)
                return reqs
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        return list(self._fallback_dict.values())

    def clear(self):
        if self._redis:
            try:
                keys = self._redis.keys("interaction:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception as e:
                logger.warning(f'Exception in interaction_service.py: {e}', exc_info=True)
                self._redis = None
        self._fallback_dict.clear()

# 2026-07-14 (Loop 3 — user-feedback-driven evolution): one-tap rejection
# reasons. Kept to a fixed, small set so the Telegram/LINE keyboard stays a
# single tap — no free-text UX for "why" beyond an explicit "other" bucket.
REJECTION_REASONS: List[Tuple[str, str]] = [
    ("too_risky", "太高風險"),
    ("wrong_ticker", "標的判斷錯誤"),
    ("bad_timing", "時機不對"),
    ("position_too_large", "部位過大"),
    ("dont_trust_thesis", "不信任論述"),
    ("other", "其他"),
]
_REJECTION_REASON_CODES = {code for code, _ in REJECTION_REASONS}

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
        self._pending_requests = RedisPendingRequests()
        
        # [Phase 1] ConversationRouter for free-form Q&A
        # 對話路由器：處理自由形式問答
        self.conversation_router = ConversationRouter(
            intent_classifier=self.intent_classifier,
            conversation_agent_factory=self._create_conversation_agent,
        )
        
        # 3. Register Callbacks for static adapters
        for adapter in self.adapters:
            if hasattr(adapter, 'register_callback'):
                adapter.register_callback(self.handle_response)
            if hasattr(adapter, 'register_text_callback'):
                adapter.register_text_callback(self.handle_text_response)

    async def handle_text_response(self, adapter: IChannelAdapter, user_id: str, text: str) -> None:
        """
        Handle a natural language text response received from a user.
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
            ver_svc = VerificationService(user_id=user_id) 
            
            # verify_any_reply returns True if it was a verification message and handled it
            logger.debug(f"InteractionService: Delegation to VerificationService for user {user_id}")
            result = await ver_svc.verify_any_reply(user_id, text)
            logger.info(f"InteractionService: VerificationService result for {user_id}: {result}")
            if result:
                logger.info(f"InteractionService: Verification logic successfully handled reply for ID: {user_id}")
                return # VerificationService sends its own confirmation message
            else:
                logger.debug(f"InteractionService: VerificationService did not match any pending verification for user {user_id}")
        except Exception as e:
            logger.error(f"InteractionService: Verification check exception: {e}", exc_info=True)

        # If still not resolved after verification attempt, it's truly unlinked
        if not resolved_user_id:
             logger.warning(f"InteractionService: Unlinked user {user_id} and no pending verification found. Sending acknowledgment.")
             # [v3.5] Generic acknowledgment for unlinked users
             msg = "✅ 系統已收到您的訊息 (Message Received)！\n由於此 ID 尚未與帳號綁定，系統目前無法進行進一步處理。請至 Dashboard 完成驗證。"
             try:
                 await adapter.send_message(user_id, msg) # Use send_message for text-only (more reliable)
             except Exception as e:
                 logger.error(f"InteractionService: Failed to send unlinked ack: {e}")
             return

        # 3. Route through ConversationRouter (Verification > Approval > Conversation)
        # 通過對話路由器處理（驗證 > 審核 > 對話）
        pending_reqs = [
            {"id": r.request_id, "title": r.title, "user_id": r.user_id}
            for r in self._pending_requests.values() 
            if r.is_pending() and (r.user_id == resolved_user_id or not r.user_id)
        ]

        # Detect channel type from adapter class
        channel_type = self._detect_channel_type(adapter)

        response = await self.conversation_router.route(
            adapter=adapter,
            channel_user_id=user_id,
            text=text,
            resolved_user_id=resolved_user_id,
            pending_requests=pending_reqs,
            channel_type=channel_type,
        )

        if response:
            try:
                await adapter.send_message(user_id, response)
            except Exception as e:
                logger.error(f"InteractionService: Failed to send response: {e}")

    @staticmethod
    def _detect_channel_type(adapter: IChannelAdapter) -> str:
        """Detect channel type from adapter class name."""
        class_name = adapter.__class__.__name__.lower()
        if "telegram" in class_name:
            return "telegram"
        elif "line" in class_name:
            return "line"
        elif "slack" in class_name:
            return "slack"
        return "unknown"

    @staticmethod
    def _create_conversation_agent(user_id: str, channel_type: str, channel_id: str):
        """
        Factory for creating ConversationAgent instances.
        建立 ConversationAgent 實例的工廠方法。

        Wires up the full cognitive memory architecture:
          STM (Redis) → Episodic (PG) → Wisdom (Volume)
        """
        from src.agents.conversation_agent import ConversationAgent
        from src.agents.persona.persona_provider import get_default_persona_provider
        from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager
        from src.infrastructure.memory.wisdom_vault import WisdomVault
        from src.infrastructure.memory.cognitive_memory import CognitiveMemoryManager
        from src.infrastructure.memory.channel_memory_manager import RedisSTMStore

        persona_provider = get_default_persona_provider()

        # Initialize Tier 3: Wisdom Vault (file-based cold storage)
        wisdom_vault = WisdomVault()

        # Initialize DIKW Distillation Engine
        stm_store = RedisSTMStore()
        cognitive_engine = CognitiveMemoryManager(
            stm=stm_store,
            episodic=None,  # Will use HybridMemory if available
            wisdom=wisdom_vault,
        )

        # Initialize Channel Memory with Cognitive engine
        channel_memory = ChannelMemoryManager(
            stm_store=stm_store,
            cognitive_engine=cognitive_engine,
        )

        return ConversationAgent(
            user_id=user_id,
            channel_type=channel_type,
            channel_id=channel_id,
            persona_provider=persona_provider,
            channel_memory=channel_memory,
            tier="smart",
        )

    async def request_approval(self, 
                          title: str, 
                          content: str, 
                          context: Optional[Dict[str, Any]] = None, 
                          timeout_seconds: int = 300,
                          user_id: Optional[str] = None) -> Any:
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
            current_req = self._pending_requests.get(req.request_id)
            if current_req:
                if current_req.status == InteractionStatus.APPROVED:
                    logger.info(f"Interaction {req.request_id} APPROVED")
                    req.status = InteractionStatus.APPROVED
                    return True, InteractionStatus.APPROVED
                if current_req.status == InteractionStatus.REJECTED:
                    logger.info(f"Interaction {req.request_id} REJECTED")
                    req.status = InteractionStatus.REJECTED
                    return False, InteractionStatus.REJECTED
            await asyncio.sleep(1) # Poll interval
            
        req.status = InteractionStatus.EXPIRED
        self._pending_requests[req.request_id] = req
        logger.warning(f"Interaction {req.request_id} EXPIRED")
        self._record_feedback(req, "expired")
        return False, InteractionStatus.EXPIRED

    def _record_feedback(
        self, req: InteractionRequest, decision: str,
        reason_code: Optional[str] = None, free_text: Optional[str] = None,
    ) -> None:
        """
        Persist one row to interaction_feedback (Loop 3). Fire-and-forget —
        a feedback-logging failure must never break the approval flow.
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            responded_in_s = (datetime.now() - req.created_at).total_seconds()
            engine = get_db_engine()
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO interaction_feedback
                            (request_id, user_id, decision, reason_code, free_text, responded_in_s, ticker)
                        VALUES (:rid, :uid, :decision, :reason_code, :free_text, :responded_in_s, :ticker)
                    """),
                    {
                        "rid": req.request_id,
                        "uid": req.user_id or "unknown",
                        "decision": decision,
                        "reason_code": reason_code,
                        "free_text": free_text,
                        "responded_in_s": responded_in_s,
                        "ticker": (req.payload or {}).get("ticker"),
                    },
                )
        except Exception as e:
            logger.warning(f"InteractionService: failed to record feedback for {req.request_id}: {e}")

    def _update_rejection_reason(self, request_id: str, reason_code: str) -> bool:
        """
        Fill in the reason_code on the rejection row already inserted by
        handle_response's REJECTED branch. Returns False if no matching
        pending-reason row exists (e.g. duplicate button tap, or the
        request wasn't actually a rejection).
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.begin() as conn:
                result = conn.execute(
                    text("""
                        UPDATE interaction_feedback
                        SET reason_code = :reason_code
                        WHERE request_id = :rid AND decision = 'rejected' AND reason_code IS NULL
                    """),
                    {"rid": request_id, "reason_code": reason_code},
                )
                return result.rowcount > 0
        except Exception as e:
            logger.warning(f"InteractionService: failed to update rejection reason for {request_id}: {e}")
            return False

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
                f"⚠️ **系統運行於安全模式 (Fail-safe Mode: {type(e).__name__})**\n\n"
                f"目前無法取得 AI 委員會的即時評估（可能是 {str(e)} 或 API 連線問題）。\n"
                "請根據下方原始觸發訊號進行判斷。"
            )
        
        # Format triggers for display
        formatted_triggers = "\n".join(
            f"  • {t}" for t in filtered_triggers
        ) if filtered_triggers else "(無觸發訊號)"

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

        # Phase 5: Broadcast to WebSocket for Dashboard Interaction
        from src.services.socket_manager import socket_manager
        await socket_manager.broadcast_to_user(req.user_id, {
            "type": "INTERACTION_REQUIRED",
            "payload": {
                "request_id": req.request_id,
                "type": req.type.value,
                "title": req.title,
                "content": alert_content,
                "actions": actions
            }
        })
        
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

        # 2026-07-14: reason-picker follow-up (Loop 3). This fires AFTER the
        # request is already REJECTED, so it must run before the
        # is_pending() gate below (which would otherwise always short-circuit
        # it — a rejected request is never "pending" anymore).
        action_lower = action.lower()
        if action_lower.startswith("reject_reason:"):
            reason_code = action_lower.split(":", 1)[1]
            if reason_code not in _REJECTION_REASON_CODES:
                logger.warning(f"InteractionService: unknown rejection reason code {reason_code!r}")
                return
            updated = self._update_rejection_reason(request_id, reason_code)
            resp_msg = "🙏 已記錄您的回饋，謝謝！" if updated else "（此請求已記錄過原因）"
            for adapter in self.adapters:
                try:
                    await adapter.send_message(req.user_id, resp_msg)
                except Exception as e:
                    logger.error(f"InteractionService: failed to ack rejection reason via {adapter}: {e}")
            return

        if not req.is_pending():
            logger.info(f"InteractionService: Request {request_id} already has status {req.status}")
            return

        # Update status
        resp_msg = ""
        reason_picker_needed = False
        if action_lower == "approve":
            req.status = InteractionStatus.APPROVED
            resp_msg = "✅ 已收到批准指令 (Action: Approved)"
            self._record_feedback(req, "approved")
        elif action_lower == "reject":
            req.status = InteractionStatus.REJECTED
            resp_msg = "❌ 已收到婉拒指令 (Action: Rejected)"
            self._record_feedback(req, "rejected")  # reason_code filled in by the follow-up tap
            reason_picker_needed = True
        else:
            logger.warning(f"InteractionService: Unknown action {action} for request {request_id}")
            return

        # Save status update back to the store
        self._pending_requests[request_id] = req
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

        # 2026-07-14 (Loop 3): one-tap reason picker, sent as a second
        # message right after the rejection ack — keeps request_approval's
        # own polling loop (which already returned False/REJECTED above)
        # unblocked by this fire-and-forget follow-up.
        if reason_picker_needed:
            reason_actions = [
                {"label": label, "data": f"action=reject_reason:{code}&id={request_id}", "style": "secondary"}
                for code, label in REJECTION_REASONS
            ]
            for adapter in target_adapters:
                try:
                    await adapter.send_alert(
                        user_id=req.user_id or "broadcast",
                        title="為什麼婉拒這筆交易？",
                        content="請點選最貼近的原因（幫助系統學習您的偏好）：",
                        actions=reason_actions,
                    )
                except Exception as e:
                    logger.error(f"InteractionService: failed to send rejection-reason picker via {adapter}: {e}")
