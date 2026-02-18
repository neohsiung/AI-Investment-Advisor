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

    async def notify_all(
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
        Sends notifications to all enabled adapters in parallel, filtered by category and channel selection.
        建立非同步任務並使用 asyncio.gather 併行發送通知。
        """
        import asyncio
        tasks = []
        adapter_names = []
        
        # Resolve target user
        target_user = user_id or os.getenv("LINE_USER_ID", "broadcast")
        capture_error = kwargs.get('capture_error', False)

        for adapter in self.adapters:
            adapter_type = adapter.__class__.__name__.lower().replace('adapter', '').replace('bot', '')
            
            # 1. Channel Filter
            if channels and not any(c.lower() in adapter_type for c in channels):
                continue
            
            # 2. Strategy Filter (Sync check is fine)
            if self.notification_filter:
                if not self.notification_filter.should_notify(adapter, category):
                    continue

            # Prepare call args
            call_kwargs = kwargs.copy()
            if capture_error:
                call_kwargs['raise_error'] = True
            
            # Add to async queue
            tasks.append(adapter.send_alert(
                user_id=target_user,
                title=title,
                content=content,
                actions=actions,
                **call_kwargs
            ))
            adapter_names.append(adapter.__class__.__name__)

        if not tasks:
            return {}

        # Execute in parallel
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = {}
        for name, res in zip(adapter_names, raw_results):
            if isinstance(res, Exception):
                logger.error(f"Notification failed for {name}: {res}")
                results[name] = (False, str(res)) if capture_error else False
            else:
                results[name] = (res, "OK" if res else "Failed") if capture_error else res
                
        return results

    @staticmethod
    def create_with_settings(settings_service) -> 'NotificationService':
        """
        Helper to create a fully configured NotificationService from a SettingsService.
        """
        from src.infrastructure.channels.channel_factory import ChannelFactory
        from src.services.notification_filters import InterestBasedFilter
        
        # Settings retrieval might be sync or async depending on implementation, 
        # but factory usually handles it.
        settings = settings_service.get_all_settings() if settings_service else {}
        adapters = ChannelFactory.create_adapters(settings)
        noti_filter = InterestBasedFilter(settings_service)
        
        return NotificationService(adapters=adapters, notification_filter=noti_filter)

    async def send_report(self, subject: str, content: str, user_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        Convenience method for sending reports asynchronously.
        發送報表的非同步便利方法。
        """
        if 'category' not in kwargs:
            kwargs['category'] = 'report'
            
        return await self.notify_all(
            title=subject,
            content=content,
            user_id=user_id,
            channels=['email', 'web'],
            **kwargs
        )
