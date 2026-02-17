import logging
import os
from typing import List, Dict, Any, Optional
from src.domain.interfaces import IChannelAdapter, INotificationFilter

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Orchestrates notifications across multi-channel adapters (LINE, Telegram, Email, etc.).
    在多管道適配器（LINE、Telegram、Email 等）之間協調通知。
    
    v3.9 Refactor: Strict Dependency Injection and Strategy Pattern.
    v3.9 重構：嚴格的相依注入與策略模式。
    """
    def __init__(
        self, 
        adapters: List[IChannelAdapter], 
        notification_filter: INotificationFilter = None
    ):
        self.adapters = adapters
        self.notification_filter = notification_filter

    def notify_all(
        self, 
        title: str, 
        content: str, 
        user_id: str = None, 
        actions: List[Dict[str, str]] = None, 
        channels: List[str] = None,
        category: str = "sentinel",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Sends notifications to all enabled adapters, filtered by category and channel selection.
        發送通知至所有啟用的適配器，並根據類別與管道選擇進行過濾。
        """
        results = {}
        # Resolve target user (fallback to broadcast if allowed by context)
        target_user = user_id or os.getenv("LINE_USER_ID", "broadcast")
        
        # Options
        capture_error = kwargs.get('capture_error', False)

        for adapter in self.adapters:
            # e.g. telegramadapter -> telegram
            adapter_type = adapter.__class__.__name__.lower().replace('adapter', '').replace('bot', '')
            
            # 1. Channel Filter (Selection by name)
            if channels and not any(c.lower() in adapter_type for c in channels):
                continue
            
            # 2. Strategy Filter (Interests, System bypass, etc.)
            if self.notification_filter:
                if not self.notification_filter.should_notify(adapter, category):
                    continue

            try:
                # Prepare call args
                call_kwargs = kwargs.copy()
                if capture_error:
                    call_kwargs['raise_error'] = True
                
                success = adapter.send_alert(
                    user_id=target_user,
                    title=title,
                    content=content,
                    actions=actions,
                    **call_kwargs
                )
                
                if capture_error:
                    results[adapter.__class__.__name__] = (success, "OK" if success else "Adapter returned False")
                else:
                    results[adapter.__class__.__name__] = success

            except Exception as e:
                logger.error(f"Notification failed for {adapter.__class__.__name__}: {e}")
                if capture_error:
                    results[adapter.__class__.__name__] = (False, str(e))
                else:
                    results[adapter.__class__.__name__] = False
                
        return results

    @staticmethod
    def create_with_settings(settings_service) -> 'NotificationService':
        """
        Helper to create a fully configured NotificationService from a SettingsService.
        """
        from src.infrastructure.channels.channel_factory import ChannelFactory
        from src.services.notification_filters import InterestBasedFilter
        
        settings = settings_service.get_all_settings() if settings_service else {}
        adapters = ChannelFactory.create_adapters(settings)
        noti_filter = InterestBasedFilter(settings_service)
        
        return NotificationService(adapters=adapters, notification_filter=noti_filter)

    def send_report(self, subject: str, content: str, user_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        Convenience method for sending reports, primarily via Email and Web channels.
        發送報表的便利方法，主要透過 Email 與網頁管道。
        """
        if 'category' not in kwargs:
            kwargs['category'] = 'report'
            
        return self.notify_all(
            title=subject,
            content=content,
            user_id=user_id,
            channels=['email', 'web'],
            **kwargs
        )
