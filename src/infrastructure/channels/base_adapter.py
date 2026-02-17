import logging
import re
from typing import List, Dict, Optional, Any, Callable
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class BaseChannelAdapter(IChannelAdapter):
    """
    Base implementation for Channel Adapters to ensure Clean Architecture parity.
    Handles callback registration and common user ID resolution helpers.
    """
    def __init__(self, default_target_id: str = None):
        self.default_target_id = (default_target_id or "").strip()
        self.callback: Optional[Callable[[str, str], None]] = None
        self.text_callback: Optional[Callable[[str, str], None]] = None

    def register_callback(self, callback_func: Callable[[str, str], None]) -> None:
        """Register button/interaction callback."""
        self.callback = callback_func

    def register_text_callback(self, callback_func: Callable[[str, str], None]) -> None:
        """Register text message callback."""
        self.text_callback = callback_func

    def _resolve_target_id(self, user_id: str) -> str:
        """
        Helper to resolve the actual channel ID.
        If user_id looks like an email or system ID, use default_target_id.
        """
        if not user_id:
            return self.default_target_id
            
        # Email pattern check
        is_email = re.match(r"[^@]+@[^@]+\.[^@]+", user_id)
        if is_email or user_id in ["system", "broadcast"]:
            return self.default_target_id
            
        return user_id

    def _trigger_callback(self, request_id: str, action: str):
        if self.callback:
            self.callback(request_id, action)

    def _trigger_text_callback(self, user_id: str, text: str):
        if self.text_callback:
            self.text_callback(self, user_id, text)

    # stubs for abstract methods
    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        return False

    def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    def authenticate(self, request: Any, **kwargs) -> bool:
        return True

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        return False

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        return {"ok": True}

    def verify_signature(self, payload: Any, headers: Dict[str, Any] = None) -> bool:
        """
        Verify the signature of an incoming webhook request.
        To be implemented by subclasses for specific platforms (Slack, LINE, Messenger).
        """
        return True
