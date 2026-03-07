import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
from src.infrastructure.channels.base_adapter import IChannelAdapter
from src.domain.interfaces import INotificationFilter

logger = setup_logger("NotificationFilter")

class InterestBasedFilter(INotificationFilter):
    """
    Filters notifications based on user interests configured per channel.
    根據每個管道設定的使用者興趣來過濾通知。
    """
    def __init__(self, settings_service: Any) -> None:
        """
        Initialize the filter with the settings service.
        使用設定服務初始化過濾器。
        """
        self.settings_service = settings_service

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
