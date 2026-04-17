import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
from src.infrastructure.channels.base_adapter import IChannelAdapter
from src.domain.interfaces import INotificationFilter

logger = setup_logger("NotificationFilter")

# Default JSONB structure for notification_routing setting
# Stored as a single JSON key in DB: { "telegram": { "default_chat_id": "...", "sentinel": {"chat_id": "..."}, ... } }
DEFAULT_ROUTING_SCHEMA = {
    "telegram": {
        "default_chat_id": "",
        "report":   {"chat_id": ""},
        "sentinel": {"chat_id": ""},
        "approval": {"chat_id": ""},
        "trading":  {"chat_id": ""},
    },
    "email": {
        "default_to": "",
        "report":   {"to": ""},
        "sentinel": {"to": ""},
        "approval": {"to": ""},
        "trading":  {"to": ""},
    },
    "line": {
        "default_user_id": "",
        "report":   {"user_id": ""},
        "sentinel": {"user_id": ""},
        "approval": {"user_id": ""},
        "trading":  {"user_id": ""},
    }
}


class InterestBasedFilter(INotificationFilter):
    """
    Filters notifications based on user interests configured per channel.
    Supports JSONB-based notification_routing for per-category recipient override.
    根據每個管道設定的使用者興趣來過濾通知，並支援 JSONB 格式的每類別接收人設定。
    """
    def __init__(self, settings_service: Any) -> None:
        """
        Initialize the filter with the settings service.
        使用設定服務初始化過濾器。
        """
        self.settings_service = settings_service

    def _get_routing(self) -> dict:
        """
        Load the JSONB notification_routing setting.
        讀取 JSONB 格式的 notification_routing 設定。
        """
        if not self.settings_service:
            return {}
        try:
            val = self.settings_service.get_setting("notification_routing")
            if isinstance(val, dict):
                return val
        except Exception:
            pass
        return {}

    def get_recipient_override(self, adapter_type: str, category: str) -> Optional[str]:
        """
        Return the per-category recipient override for a given adapter type.
        Returns None if no override is set (caller should use default from adapter config).

        Returns:
          - For telegram: the overriding chat_id string or None
          - For email: the overriding 'to' address string or None
          - For line: the overriding user_id string or None
        """
        routing = self._get_routing()
        channel_routing = routing.get(adapter_type, {})
        category_config = channel_routing.get(category, {})

        # Field name depends on adapter type
        field_map = {"telegram": "chat_id", "email": "to", "line": "user_id"}
        field = field_map.get(adapter_type, "chat_id")

        override = category_config.get(field, "")
        return override.strip() if override and override.strip() else None

    def should_notify(self, adapter: IChannelAdapter, category: str) -> bool:
        """
        Determine if a notification should be sent based on user interests.
        根據使用者興趣決定是否應發送通知。
        """
        if category == "system":
            return True
            
        if not self.settings_service:
            return True # Fallback if no settings service available
            
        # Resolve adapter type name: e.g. EmailAdapter -> email
        adapter_type = adapter.__class__.__name__.lower().replace('adapter', '').replace('bot', '')
        
        interests_str = self.settings_service.get_setting(f"channel_{adapter_type}_interests", "sentinel,report,approval")
        interests = [i.strip().lower() for i in interests_str.split(",") if i.strip()]
        
        if category.lower() in interests:
            return True
            
        logger.info(f"InterestBasedFilter: Filtered out {adapter_type} for category '{category}'. Interests: {interests}")
        return False
