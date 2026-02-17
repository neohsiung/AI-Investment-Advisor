import logging
import os
from typing import List, Dict, Any
from src.domain.interfaces import IChannelAdapter
from src.notifier import EmailNotifier
from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = logging.getLogger(__name__)

class EmailAdapter(BaseChannelAdapter):
    """
    Adapter for Email notifications.
    Wraps existing EmailNotifier.
    """
    
    def __init__(self, smtp_config: Dict[str, Any] = None):
        super().__init__()
        # If config is provided, use it to initialize the notifier
        if smtp_config:
            self.notifier = EmailNotifier(smtp_config=smtp_config)
            self.is_active = True
        else:
            # Fallback for core/legacy compatibility
            self.notifier = EmailNotifier()
            self.is_active = bool(self.notifier.sender_email and self.notifier.sender_password)
    
    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message (Email).
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
        Send an email report/alert.
        """
        # Note: Email ignores actions in a raw sense, but we can append them as links if provided
        body = content
        if actions:
            body += "\n\n### Actions\n"
            for action in actions:
                label = action.get("label", "Action")
                # eToro link logic for consistency with Sentinel
                if action.get("data") == "action=etoro_link":
                    body += f"- [{label}](https://www.etoro.com/watchlists)\n"
                else:
                    body += f"- {label}\n"

        return self.notifier.send_report(title, body, to_email=kwargs.get("to_email"))
