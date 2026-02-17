import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

from src.infrastructure.channels.base_adapter import BaseChannelAdapter

class TelegramAdapter(BaseChannelAdapter):
    """
    Telegram Adapter using Bot API.
    Handles Alerts and Callbacks.
    """
    def __init__(self, bot_token: str = None, chat_id: str = None):
        import os
        super().__init__(default_target_id=chat_id)
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = self.default_target_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.is_active = bool(self.bot_token and self.chat_id)

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
        Send message to Telegram.
        user_id arg overrides self.chat_id if provided.
        """
        # Use Base helper to resolve target_chat_id
        target_chat_id = self._resolve_target_id(user_id)
        
        if not self.base_url or not target_chat_id:
            return False

        url = f"{self.base_url}/sendMessage"
        
        text_body = f"*{title}*\n\n{content}"
        
        payload = {
            "chat_id": target_chat_id,
            "text": text_body,
            "parse_mode": "Markdown"
        }

        # Add Inline Keyboard
        if actions:
            keyboard_buttons = []
            # Telegram rows usually have 2-3 buttons. Let's arrange them.
            row = []
            for action in actions:
                row.append({
                    "text": action.get("label", "Click"),
                    "callback_data": action.get("data", "")[:64] # Telegram limit 64 chars
                })
                if len(row) >= 2:
                    keyboard_buttons.append(row)
                    row = []
            if row:
                keyboard_buttons.append(row)
                
            payload["reply_markup"] = {
                "inline_keyboard": keyboard_buttons
            }

        raise_error = kwargs.get("raise_error", False)

        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            if data.get("ok"):
                logger.info(f"Telegram message sent to {target_chat_id}")
                return True
            else:
                desc = data.get('description', 'Unknown error')
                error_msg = f"Telegram API error: {desc}"
                if "chat not found" in desc.lower():
                    error_msg += " (Hint: Check if your Chat ID is correct and you have started the bot)"
                
                logger.error(error_msg)
                if raise_error:
                    raise ValueError(error_msg)
                return False
        except Exception as e:
            logger.error(f"TelegramAdapter exception: {e}")
            if raise_error:
                raise e
            return False
    
    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Telegram Callback Query.
        """
        # 1. Handle Callback Query (Buttons)
        callback_query = payload.get("callback_query")
        if callback_query:
            query_id = callback_query.get("id")
            data = callback_query.get("data") # e.g. "action=approve&id=123"
            
            # Parse data
            params = {}
            if data:
                for part in data.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = v
            
            request_id = params.get("id")
            action = params.get("action")
            
            if self.callback and request_id and action:
                logger.info(f"Telegram Callback: {action} for {request_id}")
                self._trigger_callback(request_id, action)
                
            # Answer callback query to stop loading animation
            if query_id and self.base_url:
                try:
                    requests.post(f"{self.base_url}/answerCallbackQuery", json={"callback_query_id": query_id})
                except Exception as e:
                    logger.error(f"Failed to answer Telegram callback: {e}")
        
        # 2. Handle Message (Text)
        message = payload.get("message")
        if message:
            chat = message.get("chat")
            text = message.get("text")
            if chat and text:
                chat_id = str(chat.get("id"))
                logger.info(f"Telegram Text: {text} from {chat_id}")
                self._trigger_text_callback(chat_id, text)
        
        return {"ok": True}
