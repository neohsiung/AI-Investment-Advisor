import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List
from src.utils.logger import setup_logger
from src.infrastructure.channels.base_adapter import BaseChannelAdapter
from src.notifier import EmailNotifier

logger = setup_logger("EmailAdapter")

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
    
    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message (Email) asynchronously.
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
        Send an email report/alert asynchronously.
        Supports per-category recipient override via notification_routing JSONB setting.
        支援每類別的接收人 override（透過 notification_routing JSONB 設定）。
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

        # Per-category 'to' email override from notification_routing JSONB
        category = kwargs.get("category", "")
        override_to = None
        if category:
            try:
                _filter = kwargs.get("_filter")
                if _filter and hasattr(_filter, "get_recipient_override"):
                    override_to = _filter.get_recipient_override("email", category)
            except Exception:
                pass

        to_email = override_to or kwargs.get("to_email")
        if not to_email and user_id and "@" in user_id:
            to_email = user_id
        return await self.notifier.send_report(title, body, to_email=to_email)

