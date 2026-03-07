from src.utils.logger import setup_logger
logger = setup_logger("NotificationService")

import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.domain.interfaces import IChannelAdapter, INotificationFilter

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
        notification_filter: INotificationFilter = None,
        user_repo = None
    ):
        self.adapters = adapters
        self.notification_filter = notification_filter
        self._user_repo = user_repo

    async def _resolve_channel_id(self, user_id: str, adapter_type: str) -> str:
        """
        Resolves a channel-specific identifier from a user UUID or legacy ID.
        從使用者 UUID 或舊版 ID 解析特定管道的識別碼。
        """
        # 1. Simple broadcast or None
        if not user_id or user_id == "broadcast":
            return user_id

        # 2. Check if it's a UUID (v4 scheme)
        import re
        is_uuid = re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', user_id.lower())
        
        target_uuid = user_id
        
        # 3. Resolve from UserIdentities
        try:
            if self._user_repo:
                user_repo = self._user_repo
            else:
                from src.repositories.user_repository import AlchemyUserRepository
                user_repo = AlchemyUserRepository()
                
            if not is_uuid:
                # If not UUID, it might be an email or another provider ID
                # Attempt to look up the UUID first
                if "@" in user_id:
                    user_data = user_repo.get_by_identity("email", user_id)
                    if user_data and "id" in user_data:
                        target_uuid = user_data["id"]
                else:
                    # Fallback if there's other logic (e.g. legacy IDs)
                    return user_id

            identities = user_repo.get_identities(target_uuid)
            
            # Map adapter type to identity provider
            # adapter_type is like 'line', 'telegram', 'email', 'messenger', 'slack', 'googlechat', 'web'
            for identity in identities:
                if identity['provider'].lower() == adapter_type.lower():
                    return identity['identifier']
            
            # Fallback to secondary identities or original UUID
            # If it's email adapter, try to find 'email' provider
            if adapter_type == 'email':
                for identity in identities:
                    if identity['is_primary']:
                        return identity['identifier']
        except Exception as e:
            logger.debug(f"Identity resolution failed for {user_id} on {adapter_type}: {e}")

        return target_uuid

    async def notify_all(
        self, 
        title: str, 
        content: str, 
        user_id: str = None, 
        actions: List[Dict[str, Any]] = None, 
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
        
        # Resolve initial user
        raw_user = user_id or os.getenv("LINE_USER_ID", "broadcast")
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

            # 3. Resolve Identity for this specific adapter
            resolved_id = await self._resolve_channel_id(raw_user, adapter_type)

            # Prepare call args
            call_kwargs = kwargs.copy()
            if capture_error:
                call_kwargs['raise_error'] = True
            
            # Add to async queue
            tasks.append(adapter.send_alert(
                user_id=resolved_id,
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
    def create_with_settings(settings_service, user_id: str = None) -> 'NotificationService':
        """
        Helper to create a fully configured NotificationService from a SettingsService.
        """
        from src.infrastructure.channels.channel_factory import ChannelFactory
        from src.services.notification_filters import InterestBasedFilter
        
        # v4.1.4: Ensure user_id is passed to get_all_settings for correct adapter config
        if settings_service and user_id:
            settings_service.user_id = user_id

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
