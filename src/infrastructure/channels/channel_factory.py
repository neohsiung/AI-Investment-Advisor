import logging
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.domain.interfaces import IChannelAdapter

# Import Adapters
from src.infrastructure.channels.line_adapter import LineBotAdapter
from src.infrastructure.channels.slack_adapter import SlackAdapter
from src.infrastructure.channels.telegram_adapter import TelegramAdapter
from src.infrastructure.channels.messenger_adapter import MessengerAdapter
from src.infrastructure.channels.google_chat_adapter import GoogleChatAdapter

logger = logging.getLogger(__name__)

class ChannelFactory:
    """
    Factory pattern for creating Channel Adapters.
    Centralizes instantiation logic and configuration injection.
    """
    
    @staticmethod
    def _parse_setting(value: typing.Any) -> typing.Any:
        """
        Parses a setting value from its string/JSON-quoted representation.
        Handles: "true" -> True, "false" -> False, '"string"' -> 'string', '123' -> 123.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value
            
        # Standardize boolean strings
        lower_val = value.strip().lower().strip('"').strip("'")
        if lower_val == "true":
            return True
        if lower_val == "false":
            return False
            
        # Attempt JSON decoding for quoted strings or numbers
        import json
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Fallback to the original string after stripping quotes
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
            return value

    @staticmethod
    def create_adapters(settings: typing.Dict[str, typing.Any]) -> typing.List[IChannelAdapter]:
        """
        Creates a list of enabled adapters based on settings.
        v3.9 Refactor: Standardized parameter extraction and injection with robust parsing.
        """
        # Parse all settings for robust typing
        parsed = {k: ChannelFactory._parse_setting(v) for k, v in settings.items()}
        
        logger.info(f"ChannelFactory: Creating adapters with {len(parsed)} keys. Enabled: "
                    f"LINE={parsed.get('channel_line_enabled')}, "
                    f"Slack={parsed.get('channel_slack_enabled')}, "
                    f"Telegram={parsed.get('channel_telegram_enabled')}")
        adapters = []
        
        # 1. LINE
        if parsed.get("channel_line_enabled") is True or parsed.get("channel_line_enabled") == "true":
            try:
                adapters.append(LineBotAdapter(
                    channel_access_token=str(parsed.get("channel_line_access_token") or ""), 
                    channel_secret=str(parsed.get("channel_line_secret") or ""),
                    line_user_id=str(parsed.get("channel_line_user_id") or "")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize LINE adapter: {e}")

        # 2. Slack
        if parsed.get("channel_slack_enabled") is True or parsed.get("channel_slack_enabled") == "true":
            try:
                adapters.append(SlackAdapter(
                    bot_token=str(parsed.get("channel_slack_bot_token") or ""), 
                    channel_id=str(parsed.get("channel_slack_channel_id") or ""),
                    signing_secret=str(parsed.get("channel_slack_signing_secret") or "")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Slack adapter: {e}")

        # 3. Telegram
        if parsed.get("channel_telegram_enabled") is True or parsed.get("channel_telegram_enabled") == "true":
            try:
                # Ensure chat_id is stringified for resolve_target_id logic
                adapters.append(TelegramAdapter(
                    bot_token=str(parsed.get("channel_telegram_bot_token") or ""), 
                    chat_id=str(parsed.get("channel_telegram_chat_id") or "")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Telegram adapter: {e}")

        # 4. Email
        if parsed.get("channel_email_enabled") is True or parsed.get("channel_email_enabled") == "true":
            try:
                from src.infrastructure.channels.email_adapter import EmailAdapter
                smtp_config = {
                    'server': parsed.get("channel_email_smtp_server"),
                    'port': parsed.get("channel_email_smtp_port", "587"),
                    'user': parsed.get("channel_email_smtp_user"),
                    'password': parsed.get("channel_email_smtp_pass"),
                    'from_address': parsed.get("channel_email_from_address"),
                    'to_address': parsed.get("channel_email_to_address")
                }
                adapters.append(EmailAdapter(smtp_config=smtp_config))
            except Exception as e:
                logger.error(f"Failed to initialize Email adapter: {e}")
        
        # 5. Messenger
        if parsed.get("channel_messenger_enabled") is True or parsed.get("channel_messenger_enabled") == "true":
            try:
                adapters.append(MessengerAdapter(
                    page_token=str(parsed.get("channel_messenger_page_token") or ""), 
                    verify_token=str(parsed.get("channel_messenger_verify_token") or ""),
                    app_secret=str(parsed.get("channel_messenger_app_secret") or "")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Messenger adapter: {e}")

        # 6. Google Chat
        if parsed.get("channel_google_chat_enabled") is True or parsed.get("channel_google_chat_enabled") == "true":
            try:
                adapters.append(GoogleChatAdapter(
                    webhook_url=str(parsed.get("channel_google_chat_webhook_url") or "")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Google Chat adapter: {e}")
        
        # 7. Always include WebAdapter for event logging / dashboard view
        try:
            from src.infrastructure.channels.web_adapter import WebAdapter
            adapters.append(WebAdapter())
        except Exception as e:
            logger.error(f"Failed to initialize Web adapter: {e}")

        return adapters
