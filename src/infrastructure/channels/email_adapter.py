import logging
from typing import List, Dict, Any
from src.domain.interfaces import IChannelAdapter
from src.notifier import EmailNotifier

logger = logging.getLogger(__name__)

class EmailAdapter(IChannelAdapter):
    """
    Adapter for Email notifications.
    Wraps existing EmailNotifier.
    """
    
    def __init__(self, notifier: EmailNotifier = None):
        self.notifier = notifier or EmailNotifier()
    
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

    def register_callback(self, callback_func: Any) -> None:
        pass

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        return {"ok": True}
