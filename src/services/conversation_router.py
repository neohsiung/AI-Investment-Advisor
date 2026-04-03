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
