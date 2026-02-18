import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = logging.getLogger(__name__)

class GoogleChatAdapter(BaseChannelAdapter):
    """
    Google Chat Adapter using Incoming Webhooks.
    """
    def __init__(self, webhook_url: str = None):
        import os
        super().__init__()
        self.webhook_url = (webhook_url or os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "")).strip()
        self.is_active = bool(self.webhook_url)

    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message.
        """
        if isinstance(message, str):
            return await self.send_alert(user_id, "Message", message)
        return False

    async def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    async def authenticate(self, request: Any, **kwargs) -> bool:
        return True

    async def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Google Chat via Webhook asynchronously.
        """
        import httpx
        target_url = self.webhook_url
        
        if not target_url:
            logger.warning("GoogleChatAdapter: Missing webhook_url. Skipping.")
            return False

        text_body = f"*{title}*\n{content}"
        payload = {"text": text_body}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(target_url, json=payload, timeout=10.0)
                if response.status_code == 200:
                    logger.info(f"Google Chat message sent.")
                    return True
                else:
                    logger.error(f"Google Chat API error: {response.status_code} {response.text}")
                    return False
        except Exception as e:
            logger.error(f"GoogleChatAdapter exception: {e}")
            return False

    async def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        # Google Chat webhooks are usually one-way for simple webhooks.
        # Apps with static endpoints are handled differently.
        return {"ok": True}
