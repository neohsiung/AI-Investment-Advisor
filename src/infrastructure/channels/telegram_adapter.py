import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class TelegramAdapter(IChannelAdapter):
    """
    Telegram Adapter using Bot API.
    Supports Inline Keyboards.
    """
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Telegram.
        user_id arg overrides self.chat_id if provided.
        """
        target_chat_id = user_id if user_id else self.chat_id
        
        if not self.base_url or not target_chat_id:
            logger.warning("TelegramAdapter: Missing token or chat_id. Skipping.")
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

        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            if data.get("ok"):
                logger.info(f"Telegram message sent to {target_chat_id}")
                return True
            else:
                logger.error(f"Telegram API error: {data.get('description')}")
                return False
        except Exception as e:
            logger.error(f"TelegramAdapter exception: {e}")
            return False
    
    def register_callback(self, callback_func):
        self.callback = callback_func

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Telegram Callback Query.
        """
        # Telegram sends update object
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
                self.callback(request_id, action)
                
            # Answer callback query to stop loading animation
            if query_id and self.base_url:
                try:
                    requests.post(f"{self.base_url}/answerCallbackQuery", json={"callback_query_id": query_id})
                except Exception as e:
                    logger.error(f"Failed to answer Telegram callback: {e}")
        
        return {"ok": True}
