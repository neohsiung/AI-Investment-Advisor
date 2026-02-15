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
    Orchestrates two-way interactions with the user across multiple channels.
    Supports Approval Workflows (Human-in-the-Loop).
    協調多通路雙向互動，支援人工審核流程。
    """

    def __init__(self, adapters: List[IChannelAdapter] = None, intent_classifier: Any = None):
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
            
        self._pending_requests: Dict[str, InteractionRequest] = {} 
        
        # 3. Register Callbacks
        for adapter in self.adapters:
            if hasattr(adapter, 'register_callback'):
                adapter.register_callback(self.handle_response)
            if hasattr(adapter, 'register_text_callback'):
                adapter.register_text_callback(self.handle_text_response)

    def handle_text_response(self, user_id: str, text: str):
        """
        Handle natural language response from user.
        Uses IntentClassifier to determine APPROVE/REJECT.
        """
        if not self.intent_classifier:
            logger.warning("No IntentClassifier configured. Ignoring text response.")
            return

        # 1. Find latest pending request for this user (or broadcast)
        pending_reqs = [
            r for r in self._pending_requests.values() 
            if r.is_pending() and (r.user_id == user_id or not r.user_id)
        ]
        
        if not pending_reqs:
            logger.info(f"No pending requests found for user {user_id}. Ignoring text.")
            return
            
        # Sort by creation time desc
        latest_req = sorted(pending_reqs, key=lambda r: r.created_at, reverse=True)[0]
        
        # 2. Classify Intent
        intent = self.intent_classifier.classify(text)
        logger.info(f"Classified text '{text}' from {user_id} as {intent}")
        
        if intent in ["APPROVE", "REJECT"]:
            # 3. Trigger standard handler
            self.handle_response(latest_req.request_id, intent.lower())
        else:
            # Optional: Send clarification asking "Did you mean approve?"
            pass

    def request_approval(self, 
                         title: str, 
                         content: str, 
                         context: Dict[str, Any] = None, 
                         timeout_seconds: int = 300,
                         user_id: str = None) -> bool:
        """
        Blocking call to request user approval.
        Sends notification and waits for response.
        
        Args:
            title: Title of the request (e.g. "Trade Approval")
            content: Details (e.g. "Buy 10 AAPL at $150?")
            context: Data payload for the callback
            timeout_seconds: How long to wait
            
        Returns:
            bool: True if APPROVED, False if REJECTED or TIMEOUT
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
        self._send_approval_request(req)
        
        # 2. Wait for Response (Polling for MVP)
        # TODO: Use Async/Await or Event Bus in production
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if req.status == InteractionStatus.APPROVED:
                logger.info(f"Interaction {req.request_id} APPROVED")
                return True
            if req.status == InteractionStatus.REJECTED:
                logger.info(f"Interaction {req.request_id} REJECTED")
                return False
            time.sleep(1) # Poll interval
            
        req.status = InteractionStatus.EXPIRED
        logger.warning(f"Interaction {req.request_id} EXPIRED")
        return False

    def _send_approval_request(self, req: InteractionRequest):
        """
        Route request to active adapters.
        """
        actions = [
            {"label": "Approve", "data": f"action=approve&id={req.request_id}", "style": "primary"},
            {"label": "Reject", "data": f"action=reject&id={req.request_id}", "style": "secondary"}
        ]
        
        for adapter in self.adapters:
            try:
                # Use adapters that support interaction
                # For now using send_alert mechanism but with actions
                adapter.send_alert(
                    user_id=req.user_id or "broadcast", # TODO: Resolve User ID
                    title=f"⚠️ {req.title}",
                    content=req.content,
                    actions=actions
                )
            except Exception as e:
                logger.error(f"Failed to send interaction via {adapter}: {e}")

    def handle_response(self, request_id: str, action: str):
        """
        Callback handler from Webhook.
        """
        req = self._pending_requests.get(request_id)
        if not req:
            logger.warning(f"Received response for unknown request {request_id}")
            return
            
        if not req.is_pending():
            logger.warning(f"Request {request_id} is no longer pending ({req.status})")
            return

        if action.lower() == "approve":
            req.status = InteractionStatus.APPROVED
        elif action.lower() == "reject":
            req.status = InteractionStatus.REJECTED
        else:
            logger.warning(f"Unknown action {action} for request {request_id}")
