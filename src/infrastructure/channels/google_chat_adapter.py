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

    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message.
        """
        if isinstance(message, str):
            return self.send_alert(user_id, "Message", message)
        return False

    def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    def authenticate(self, request: Any, **kwargs) -> bool:
        return True

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Google Chat via Webhook.
        user_id is ignored as Webhook targets a specific space associated with the link.
        """
        # If user_id is provided and looks like a URL, maybe override? 
        # For now, rely on self.webhook_url configured in Settings.
        target_url = self.webhook_url
        
        if not target_url:
            logger.warning("GoogleChatAdapter: Missing webhook_url. Skipping.")
            return False

        # Simple Text Message
        text_body = f"*{title}*\n{content}"
        
        payload = {
            "text": text_body
        }

        # If actions, append links or simulated buttons (Webhook doesn't support interactive cards fully without App ID)
        # But we can add widgets if using Card v2...
        # For Webhooks, standard Cards v2 are supported.
        if actions:
             widgets = []
             for action in actions:
                 # Since we don't have a callback server for Google Chat (requires verifying signature etc vs just simple webhook),
                 # Interactive buttons that hit OUR callback might be tricky via simple webhook configuration.
                 # Usually Google Chat Apps use pub/sub or http endpoint.
                 # For simple Webhook, interactivity is limited.
                 # Let's fallback to Text Links " Click Here for [Action] " if interactivity is complex.
                 # Or just render buttons that link to a URL (e.g. valid approval URL if we had one).
                 # For now, let's just append text instructions.
                 pass
             
             # Fallback: Just append actions as text
             # payload["text"] += "\n[Actions not fully supported in Webhook Mode]"

        try:
            response = requests.post(target_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Google Chat message sent.")
                return True
            else:
                logger.error(f"Google Chat API error: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"GoogleChatAdapter exception: {e}")
            return False

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        # Google Chat webhooks are usually one-way for simple webhooks.
        # Apps with static endpoints are handled differently.
        return {"ok": True}
