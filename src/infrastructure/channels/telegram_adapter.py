"""
Fixed TelegramAdapter - reads per-user Telegram settings from PostgreSQL
instead of relying on environment variables.

Key changes:
1. __init__ no longer reads env variables
2. send_alert() dynamically queries DB for user's Telegram token and chat_id
3. Maintains backward compatibility with send_message_sync/send_alert_sync
4. HTML content auto-stripped to clean Telegram-friendly text
"""

import os
import typing
import re
from html.parser import HTMLParser
from typing import List, Dict, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
logger = setup_logger("TelegramAdapter")

from src.infrastructure.channels.base_adapter import BaseChannelAdapter


class _TelegramHTMLFormatter(HTMLParser):
    """
    Format HTML to Telegram-compatible HTML representation.
    將 HTML 格式化為 Telegram 相容的 HTML 表達。
    """
    def __init__(self):
        super().__init__()
        self._output_parts = []
        self._skip = False
        self._allowed_tags = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'a'}
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip = True
            return
        if self._skip:
            return

        if tag in self._allowed_tags:
            # Reconstruct tag with attributes (e.g. href for <a>)
            # 重構帶有屬性的標記（例如 <a> 的 href）
            self._tag_stack.append(tag)
            if tag == 'a':
                href = next((val for name, val in attrs if name == 'href'), '')
                if href:
                    self._output_parts.append(f'<a href="{href}">')
                else:
                    self._output_parts.append('<a>')
            else:
                self._output_parts.append(f'<{tag}>')
        elif tag in ('p', 'br', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._output_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._skip = False
            return
        if self._skip:
            return

        if tag in self._allowed_tags:
            if self._tag_stack and self._tag_stack[-1] == tag:
                self._tag_stack.pop()
                self._output_parts.append(f'</{tag}>')
        elif tag in ('p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._output_parts.append('\n')

    def handle_data(self, data):
        if not self._skip:
            # Escape raw text data for safety inside Telegram HTML
            # 為 Telegram HTML 安全性轉義原始文字數據
            import html as _html
            self._output_parts.append(_html.escape(data))

    def get_text(self) -> str:
        # Close any unclosed tags
        # 關閉任何未關閉的標記
        while self._tag_stack:
            tag = self._tag_stack.pop()
            self._output_parts.append(f'</{tag}>')

        raw = ''.join(self._output_parts)
        # Collapse 3+ newlines to 2
        # 將三個以上的換行符縮減為兩個
        raw = re.sub(r'\n{3,}', '\n\n', raw)
        # Strip each line while keeping formatting tags
        # 在保留格式化標記的同時，清除每行的首尾空白
        lines = [l.strip() for l in raw.split('\n')]
        return '\n'.join(l for l in lines if l)


def _html_to_telegram_html(html_content: str) -> str:
    """
    Convert full HTML documents to clean Telegram-friendly HTML representation.
    Handles <!DOCTYPE html>, <html>, <body> wrapped reports.

    將完整 HTML 文件轉換為乾淨的 Telegram 相容 HTML 表達方式。
    處理 <!DOCTYPE html>、<html>、<body> 包裹的報告。
    """
    if not html_content:
        return html_content

    trimmed = html_content.strip()

    # Only process if it looks like full HTML (doctype or <html tag)
    is_full_html = trimmed.lower().startswith('<!doctype') or trimmed.lower().startswith('<html')
    if not is_full_html and '<!DOCTYPE' not in trimmed and '<html' not in trimmed[:100]:
        return html_content  # Not full HTML, return as-is

    formatter = _TelegramHTMLFormatter()
    formatter.feed(trimmed)
    text = formatter.get_text()

    # Truncate to a reasonable Telegram message size (4096 char limit for HTML)
    TELEGRAM_MAX = 4000
    if len(text) > TELEGRAM_MAX:
        text = text[:TELEGRAM_MAX-200] + '\n\n... (truncated)'

    return text


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
        Auto-strips HTML from report content for clean Telegram display.
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

        # 4. Prepare message — strip HTML if needed, format for Telegram
        # 4. 準備訊息 — 依需求剝離 HTML，格式化為 Telegram 可接受格式
        is_html_doc = False
        if content:
            trimmed = content.strip()
            is_html_doc = trimmed.lower().startswith('<!doctype') or trimmed.lower().startswith('<html') or '<!DOCTYPE' in trimmed or '<html' in trimmed[:100]

        if is_html_doc:
            try:
                # If it's a full HTML report, convert and sanitize it to Telegram HTML
                # 如果是完整 HTML 報告，轉換並過濾為 Telegram HTML
                safe_content = _html_to_telegram_html(content)
            except Exception as e:
                logger.warning(f"HTML conversion failed, using raw content: {e}")
                safe_content = html.escape(content)
        else:
            # If it's plain text/markdown, escape raw text first
            # 如果是純文字或 Markdown，先轉義原始文字
            safe_content = html.escape(content)
            # Then convert markdown to HTML (Telegram parse_mode=HTML)
            # 然後將 markdown 轉換為 HTML (Telegram parse_mode=HTML)
            safe_content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', safe_content)
            safe_content = re.sub(r'__(.+?)__', r'<i>\1</i>', safe_content)

        safe_title = html.escape(title)
        text_body = f"<b>{safe_title}</b>\n\n{safe_content}"

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