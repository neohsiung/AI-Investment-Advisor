import logging
import os
from typing import List, Dict, Any, Optional
from src.domain.interfaces import IChannelAdapter
from src.infrastructure.channels.line_adapter import LineBotAdapter
from src.infrastructure.channels.email_adapter import EmailAdapter
from src.infrastructure.channels.web_adapter import WebAdapter

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Omni-channel Notification Orchestrator.
    Handles routing alerts to multiple channels (LINE, Email, Web, etc.).
    全通路通知編排器。負責將警報路由至多個管道。
    """

    def __init__(self, adapters: List[IChannelAdapter] = None):
        if adapters:
            self.adapters = adapters
        else:
            # Default adapters
            self.adapters = [
                LineBotAdapter(),
                EmailAdapter(),
                WebAdapter()
            ]
        
    def notify_all(
        self, 
        title: str, 
        content: str, 
        user_id: str = None, 
        actions: List[Dict[str, str]] = None, 
        channels: List[str] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send notification to all registered (or filtered) channels.
        
        Args:
            title: Notification title.
            content: Main text content (Markdown supported for Email/Web).
            user_id: Target user ID (identifier for the channel).
            actions: Action buttons/links.
            channels: Optional list of channel types to use (e.g. ['line', 'email']).
            **kwargs: Extra parameters passed to adapters (e.g. level, source).
            
        Returns:
            Dict[str, bool]: Success status per channel class name.
        """
        results = {}
        target_user = user_id or os.getenv("LINE_USER_ID", "broadcast")
        
        for adapter in self.adapters:
            adapter_name = adapter.__class__.__name__.lower()
            
            # Filter by channel names if provided
            if channels and not any(c.lower() in adapter_name for c in channels):
                continue
            
            try:
                success = adapter.send_alert(
                    user_id=target_user,
                    title=title,
                    content=content,
                    actions=actions,
                    **kwargs
                )
                results[adapter.__class__.__name__] = success
            except Exception as e:
                logger.error(f"Notification failed for {adapter.__class__.__name__}: {e}")
                results[adapter.__class__.__name__] = False
                
        return results

    def send_report(self, subject: str, content: str, user_id: str = None, **kwargs):
        """
        Convenience method for sending reports (primarily via Email and Web).
        """
        return self.notify_all(
            title=subject,
            content=content,
            user_id=user_id,
            channels=['email', 'web'],
            **kwargs
        )
