"""
Unified Memory Service — Multi-Channel Context Aggregation.
統一記憶服務 — 跨通道上下文聚合 [Phase 5A].

Single users may bind multiple channels (e.g., Telegram and LINE).
This service aggregates short-term memory (STM) and metadata across all
bound channels to ensure cross-channel identity and context consistency.

遵循規範:
  - 規範一 (Clean Architecture): Service Layer 封裝跨 Repository 邏輯
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範十五 (AI-Support First): Aggregates context for LLM prompts
"""

import logging
from typing import List, Dict, Any

from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class UnifiedMemoryService:
    """
    Service for aggregating user memory across all bound channels.
    跨綁定通道聚合使用者記憶的服務。
    """

    def __init__(
        self,
        memory_manager: ChannelMemoryManager,
        settings_service: SettingsService,
    ):
        """
        Args:
            memory_manager: Base channel STM/LTM manager
            settings_service: Service to retrieve user channel bindings
        """
        self._memory = memory_manager
        self._settings = settings_service

    def get_unified_short_term(
        self, user_id: str, limit_per_channel: int = 5
    ) -> List[Dict[str, str]]:
        """
        Retrieve and aggregate recent STM messages from all bound channels.
        獲取並聚合所有綁定通道的近期短期記憶訊息。

        Messages are annotated with their source channel (e.g., [TG], [LINE]).

        Args:
            user_id: Internal system user ID
            limit_per_channel: Max messages to retrieve per channel

        Returns:
            List of OpenAI-compatible message dictionaries
        """
        channel_ids_dict = self._settings.get_channel_ids_for_user(user_id)
        if not channel_ids_dict:
            logger.debug(f"UnifiedMemoryService: No channels bound for {user_id}")
            return []

        all_msgs = []
        for ch_type, ch_id in channel_ids_dict.items():
            # Get messages for this specific channel
            msgs = self._memory.get_short_term_as_messages(
                ch_id, limit=limit_per_channel
            )
            
            # Annotate content with channel prefix
            prefix = f"[{ch_type.upper()}] "
            for m in msgs:
                # Avoid double prefixing if already prefixed
                if not str(m.get("content", "")).startswith(prefix):
                    m["content"] = f"{prefix}{m.get('content', '')}"
                # Inject a meta-field for sorting/display
                m["_source_channel"] = ch_type

            all_msgs.extend(msgs)

        # In a perfect world, we'd sort by timestamp. 
        # Since STM current implementation lists are ordered chronologically per channel,
        # we interleave or just return them. For simplicity, we return them grouped by channel.
        # The LLM is capable of understanding "Here are recent things said on TG, and on LINE".
        
        logger.info(
            f"UnifiedMemoryService: Aggregated {len(all_msgs)} messages "
            f"across {list(channel_ids_dict.keys())} for {user_id}"
        )
        return all_msgs

    def get_unified_metadata(self, user_id: str, key: str) -> Any:
        """
        Search all bound channels for a specific metadata key.
        Return the first found value.
        """
        channel_ids_dict = self._settings.get_channel_ids_for_user(user_id)
        for ch_type, ch_id in channel_ids_dict.items():
            val = self._memory.get_metadata(ch_id, key)
            if val is not None:
                return val
        return None
