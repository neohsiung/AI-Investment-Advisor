"""
Channel Gateway — Unified Messaging Infrastructure [Phase 7].
頻道閘道器 — 統一訊息基礎設施。

Provides a unified interface for cross-channel message routing, token-aware 
context management, and DIKW (Data-Information-Knowledge-Wisdom) triggers.

核心職責:
1. 統一出站介面: 封裝 NotificationService，支援多管道發送。
2. 統一入站掛鉤: 提供標準化訊息處理入口，整合對話 Agent。
3. DIKW 觸發: 監控對話長度與 Token 消耗，自動觸發記憶壓縮。

遵循規範:
  - 規範一 (Clean Architecture): Infrastructure 層級的通訊門面系統。
  - 規範七 (DIKW 模型): 實作數據蒸餾觸發機制。
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from src.services.notification_service import NotificationService
from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager

logger = logging.getLogger(__name__)

class ChannelGateway:
    """
    Central hub for managing multi-channel communication and memory evolution.
    """
    
    def __init__(
        self, 
        notification_service: NotificationService,
        memory_manager: ChannelMemoryManager
    ):
        self.notifier = notification_service
        self.memory = memory_manager
        
        # Mapping for conversation-specific agents to maintain stateful conversations
        self._active_agents = {}
        
        # DIKW Thresholds (Configurable)
        self.compression_token_threshold = 4000 # ~10-20 turns
        self.message_count_threshold = 20

    async def send_message(
        self, 
        user_id: str, 
        channel_type: str, 
        channel_id: str, 
        text: str,
        **kwargs
    ) -> bool:
        """
        Routes an outbound message to a specific channel.
        將出站訊息路由至特定頻道。
        """
        logger.info(f"ChannelGateway: Sending message to {user_id} via {channel_type} ({channel_id})")
        
        # Record into STM before sending (Agent usually does this, 
        # but Gateway ensures all outgoing traffic is tracked)
        self.memory.append_short_term(channel_id, "assistant", text)
        
        # Call NotificationService
        # We specify the exact channel to avoid broadcasting to all bound channels
        results = await self.notifier.notify_all(
            title="", # Empty title for chat
            content=text,
            user_id=channel_id, # Target specific channel identity
            channels=[channel_type],
            **kwargs
        )
        
        # Check if at least the target channel succeeded
        success = any(results.values())
        
        # [Phase 7.2] Trigger token check after sending
        await self._check_dikw_evolution(user_id, channel_id)
        
        return success

    async def handle_inbound_message(
        self, 
        user_id: str, 
        channel_type: str, 
        channel_id: str, 
        text: str,
        **kwargs
    ):
        """
        Standardized entry point for messages from LINE, Telegram, or Webhooks.
        標準化的入站訊息進入點。
        """
        logger.debug(f"ChannelGateway: Inbound from {channel_type}/{channel_id}: {text[:50]}...")
        
        # 1. Record User Message
        self.memory.append_short_term(channel_id, "user", text)
        
        # 2. Get or Create Agent for this user-channel pair
        agent_key = f"{user_id}:{channel_type}:{channel_id}"
        if agent_key not in self._active_agents:
            from src.agents.conversation_agent import ConversationAgent
            from src.agents.persona.persona_provider import PersonaProvider
            
            # TODO: SettingsService should be injected or passed
            self._active_agents[agent_key] = ConversationAgent(
                user_id=user_id,
                channel_type=channel_type,
                channel_id=channel_id,
                persona_provider=PersonaProvider(),
                channel_memory=self.memory
            )
        
        agent = self._active_agents[agent_key]
        
        # 3. Process with Agent
        # Note: Response handling might be async or streaming. Here we assume one-shot for now.
        response_text = await agent.respond(text)
        
        # 4. Route back
        await self.send_message(user_id, channel_type, channel_id, response_text)

    async def _check_dikw_evolution(self, user_id: str, channel_id: str):
        """
        Evaluates conversation depth and triggers DIKW distillation if needed.
        評估對話深度並在需要時觸發 DIKW 蒸餾。
        """
        # Current logic: Simple count-based trigger
        # Future logic: Real token counting via tiktoken
        history = self.memory.get_short_term(channel_id)
        count = len(history)
        
        if count >= self.message_count_threshold:
            logger.info(f"ChannelGateway: DIKW Trigger - Conv {channel_id} reached {count} msgs. Compressing...")
            
            # Start Background Distillation
            asyncio.create_task(self._distill_context(user_id, channel_id))

    async def _distill_context(self, user_id: str, channel_id: str):
        """
        Data -> Information -> Knowledge distillation process.
        資料 -> 資訊 -> 知識的蒸餾過程。
        """
        try:
            from src.services.cognitive_memory_manager import CognitiveMemoryManager
            cmm = CognitiveMemoryManager(user_id=user_id)
            
            # Distill STM into LTM and Wisdom
            # This follows Phase 7 architecture: STM -> Summary -> Vectors -> Wisdom
            summary = await cmm.distill_conversation(channel_id)
            
            # [Phase 7.3] Wisdom Hub injection could happen here
            logger.info(f"ChannelGateway: DIKW Distillation complete for {channel_id}. Summary length: {len(summary)}")
            
        except Exception as e:
            logger.error(f"ChannelGateway: DIKW Distillation failed: {e}")

# Global singleton or per-app context
_gateway: Optional[ChannelGateway] = None

def get_gateway(notifier=None, memory=None) -> ChannelGateway:
    global _gateway
    if not _gateway:
        if not notifier or not memory:
            raise ValueError("ChannelGateway: Initial creation requires notifier and memory.")
        _gateway = ChannelGateway(notifier, memory)
    return _gateway
