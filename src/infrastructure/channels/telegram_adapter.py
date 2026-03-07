import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List
from src.utils.logger import setup_logger
logger = setup_logger("TelegramAdapter")

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
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.default_target_id = self.chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.is_active = bool(self.bot_token and self.chat_id)

    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message asynchronously.
        """
        if isinstance(message, str):
            return await self.send_alert(user_id, "Message", message)
        return False
    
    def send_message_sync(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message synchronously (for backward compatibility).
        同步發送訊息（向後相容）。
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.send_message(user_id, message, **kwargs))
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.send_message(user_id, message, **kwargs))
        except Exception as e:
            logger.error(f"Sync send_message failed: {e}")
            return False

    async def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    async def authenticate(self, request: Any, **kwargs) -> bool:
        return True

    async def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Telegram via Bot API asynchronously.
        """
        import httpx
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

        if actions:
            keyboard_buttons = []
            row = []
            for action in actions:
                row.append({
                    "text": action.get("label", "Click"),
                    "callback_data": action.get("data", "")[:64]
                })
                if len(row) >= 2:
                    keyboard_buttons.append(row)
                    row = []
            if row:
                keyboard_buttons.append(row)
                
            payload["reply_markup"] = {"inline_keyboard": keyboard_buttons}

        raise_error = kwargs.get("raise_error", False)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, timeout=10.0)
                data = response.json()
                if data.get("ok"):
                    logger.info(f"Telegram message sent to {target_chat_id}")
                    return True
                else:
                    error_msg = f"Telegram API error: {data.get('description', 'Unknown error')}"
                    logger.error(error_msg)
                    if raise_error:
                        raise ValueError(error_msg)
                    return False
        except Exception as e:
            logger.error(f"TelegramAdapter exception: {e}")
            if raise_error:
                raise e
            return False
    
    def send_alert_sync(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send alert to Telegram synchronously (for backward compatibility).
        同步發送警報到 Telegram（向後相容）。
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create a new task in a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.send_alert(user_id, title, content, actions, **kwargs)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.send_alert(user_id, title, content, actions, **kwargs)
                )
        except Exception as e:
            logger.error(f"Sync send_alert failed: {e}")
            if kwargs.get("raise_error", False):
                raise e
            return False
    
    async def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Telegram Callback Query asynchronously.
        """
        import httpx
        callback_query = payload.get("callback_query")
        if callback_query:
            query_id = callback_query.get("id")
            data = callback_query.get("data")
            
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
                await self._trigger_callback(request_id, action)
                
            if query_id and self.base_url:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(f"{self.base_url}/answerCallbackQuery", json={"callback_query_id": query_id}, timeout=5.0)
                except Exception as e:
                    logger.error(f"Failed to answer Telegram callback: {e}")
        
        message = payload.get("message")
        if message:
            chat = message.get("chat")
            text = message.get("text")
            if chat and text:
                chat_id = str(chat.get("id"))
                logger.info(f"Telegram Text: {text} from {chat_id}")
                await self._trigger_text_callback(chat_id, text)
        
        return {"ok": True}
        
