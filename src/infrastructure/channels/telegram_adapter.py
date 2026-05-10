"""
Fixed TelegramAdapter - reads per-user Telegram settings from PostgreSQL
instead of relying on environment variables.

Key changes:
1. __init__ no longer reads env variables
2. send_alert() dynamically queries DB for user's Telegram token and chat_id
3. Maintains backward compatibility with send_message_sync/send_alert_sync
"""

import os
import typing
import re
from typing import List, Dict, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
logger = setup_logger("TelegramAdapter")

from src.infrastructure.channels.base_adapter import BaseChannelAdapter

class TelegramAdapter(BaseChannelAdapter):
    """
    Telegram Adapter using Bot API.
    Reads per-user Telegram settings from PostgreSQL settings table.
    Handles Alerts and Callbacks.
    """
    def __init__(self, bot_token: str = None, chat_id: str = None):
        """
        Initialize adapter.
        v10.0: Store parameters as fallback if DB query fails.
        """
        super().__init__(default_target_id=chat_id)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = None
        self.is_active = True  # Always active - will validate at send time
        
        # Database connection pool (lazy initialized)
        self._db_pool = None

    async def _get_db_pool(self):
        """Lazy initialize database connection pool."""
        if self._db_pool is None:
            try:
                import asyncpg
                # Try DATABASE_URL first, then build from DB_* env vars
                db_url = os.getenv("DATABASE_URL", "")
                if not db_url:
                    # Build connection string from individual DB_* env vars
                    db_user = os.getenv("DB_USER", "postgres")
                    db_pass = os.getenv("DB_PASS", os.getenv("DB_PASSWORD", "postgres"))
                    db_host = os.getenv("DB_HOST", "localhost")
                    db_port = os.getenv("DB_PORT", "5432")
                    db_name = os.getenv("DB_NAME", "advisor_prod")
                    db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                
                if db_url:
                    self._db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
                    logger.info(f"Database pool created: {db_url.split('@')[1] if '@' in db_url else 'unknown'}")
            except Exception as e:
                logger.error(f"Failed to create DB pool: {e}")
        return self._db_pool

    async def _get_user_telegram_settings(self, user_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Query PostgreSQL to get user's Telegram bot token and chat ID.
        Returns: (bot_token, chat_id)
        """
        try:
            pool = await self._get_db_pool()
            if not pool:
                logger.error("No database pool available")
                return None, None

            async with pool.acquire() as connection:
                # 1. Try primary keys (consistent with UI/ChannelFactory)
                bot_token_row = await connection.fetchval(
                    "SELECT value FROM settings WHERE user_id = $1 AND key = $2",
                    user_id, "channel_telegram_bot_token"
                )
                
                chat_id_row = await connection.fetchval(
                    "SELECT value FROM settings WHERE user_id = $1 AND key = $2",
                    user_id, "channel_telegram_chat_id"
                )
                
                # 2. Fallback to legacy keys
                if not bot_token_row:
                    bot_token_row = await connection.fetchval(
                        "SELECT value FROM settings WHERE user_id = $1 AND key = $2",
                        user_id, "notification_telegram_bot_token"
                    )
                if not chat_id_row:
                    chat_id_row = await connection.fetchval(
                        "SELECT value FROM settings WHERE user_id = $1 AND key = $2",
                        user_id, "notification_telegram_chat_id"
                    )
                
                bot_token = self._clean_db_value(bot_token_row)
                chat_id = self._clean_db_value(chat_id_row)
                
                return bot_token, chat_id
        except Exception as e:
            logger.error(f"Failed to get user Telegram settings: {e}")
            return None, None

    @staticmethod
    def _clean_db_value(raw: Optional[str]) -> Optional[str]:
        """Strip JSON quotes and decrypt ENC: values from asyncpg."""
        if not raw:
            return None
        import json as _json
        val = raw.strip()
        # asyncpg may return JSON-serialised strings: '"ENC:xxx"' or '"12345"'
        if val.startswith('"') and val.endswith('"'):
            try:
                val = _json.loads(val)
            except (ValueError, TypeError):
                pass
        # Decrypt ENC: prefix using APP_SECRET_KEY
        if isinstance(val, str) and val.startswith("ENC:"):
            try:
                from src.services.llm_credential_cipher import LLMCredentialCipher
                cipher = LLMCredentialCipher()
                decrypted = cipher.decrypt(val)
                if decrypted:
                    val = decrypted
            except Exception:
                pass  # Return as-is if decryption fails
        return val if val else None

    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """Send a generic message asynchronously."""
        if isinstance(message, str):
            return await self.send_alert(user_id, "Message", message)
        return False
    
    def send_message_sync(self, user_id: str, message: Any, **kwargs) -> bool:
        """Send a generic message synchronously (for backward compatibility)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
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
        Dynamically fetches user's Telegram token and chat ID from PostgreSQL.
        """
        import httpx
        import html
        
        category = kwargs.get("category", "")
        raise_error = kwargs.get("raise_error", False)

        # 1. Get user's Telegram settings from DB
        bot_token, chat_id = await self._get_user_telegram_settings(user_id)
        
        # Fallback to constructor values if DB lookup fails
        bot_token = bot_token or self.bot_token
        chat_id = chat_id or self.chat_id
        
        if not bot_token or not chat_id:
            error_msg = f"Telegram settings not found for user {user_id} and no fallback provided"
            logger.error(error_msg)
            if raise_error:
                raise ValueError(error_msg)
            return False

        # 2. Build API URL
        base_url = f"https://api.telegram.org/bot{bot_token}"
        url = f"{base_url}/sendMessage"
        
        # 3. Per-category override check (if needed)
        override_chat_id = None
        if category:
            try:
                from src.services.notification_filters import InterestBasedFilter
                _filter = kwargs.get("_filter")
                if _filter and hasattr(_filter, "get_recipient_override"):
                    override_chat_id = _filter.get_recipient_override("telegram", category)
            except Exception:
                pass

        target_chat_id = override_chat_id or chat_id
        
        if not target_chat_id:
            logger.error(f"No target chat ID for user {user_id}")
            return False

        # 4. Prepare message
        safe_title = html.escape(title)
        clean_content = html.escape(content)
        
        # Convert markdown to HTML
        clean_content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', clean_content)
        clean_content = re.sub(r'__(.+?)__', r'<i>\1</i>', clean_content)
        
        text_body = f"<b>{safe_title}</b>\n\n{clean_content}"
        
        payload = {
            "chat_id": target_chat_id,
            "text": text_body,
            "parse_mode": "HTML"
        }

        # 5. Add buttons if provided
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

        # 6. Send via Telegram Bot API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, timeout=10.0)
                data = response.json()
                if data.get("ok"):
                    logger.info(f"Telegram message sent to {target_chat_id} for user {user_id}")
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
        """Send alert to Telegram synchronously (for backward compatibility)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
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
        """Handle Telegram Callback Query asynchronously."""
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
                
            if query_id:
                # Note: We don't have bot_token here, need to pass it somehow
                # For now, skip the callback answer
                pass
        
        message = payload.get("message")
        if message:
            chat = message.get("chat")
            text = message.get("text")
            if chat and text:
                chat_id = str(chat.get("id"))
                logger.info(f"Telegram Text: {text} from {chat_id}")
                import asyncio
                asyncio.create_task(self._trigger_text_callback(chat_id, text))
        
        return {"ok": True}
