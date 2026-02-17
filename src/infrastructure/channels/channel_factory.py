import logging
from typing import List, Dict, Optional
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
    def create_adapters(settings: Dict[str, str]) -> List[IChannelAdapter]:
        """
        Creates a list of enabled adapters based on settings.
        v3.9 Refactor: Standardized parameter extraction and injection.
        """
        adapters = []
        
        # 1. LINE
        if settings.get("channel_line_enabled", "false") == "true":
            try:
                adapters.append(LineBotAdapter(
                    channel_access_token=settings.get("channel_line_access_token"), 
                    channel_secret=settings.get("channel_line_secret"),
                    line_user_id=settings.get("channel_line_user_id")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize LINE adapter: {e}")

        # 2. Slack
        if settings.get("channel_slack_enabled", "false") == "true":
            try:
                adapters.append(SlackAdapter(
                    bot_token=settings.get("channel_slack_bot_token"), 
                    channel_id=settings.get("channel_slack_channel_id"),
                    signing_secret=settings.get("channel_slack_signing_secret")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Slack adapter: {e}")

        # 3. Telegram
        if settings.get("channel_telegram_enabled", "false") == "true":
            try:
                adapters.append(TelegramAdapter(
                    bot_token=settings.get("channel_telegram_bot_token"), 
                    chat_id=settings.get("channel_telegram_chat_id")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Telegram adapter: {e}")

        # 4. Email
        if settings.get("channel_email_enabled", "false") == "true":
            try:
                from src.infrastructure.channels.email_adapter import EmailAdapter
                smtp_config = {
                    'server': settings.get("channel_email_smtp_server"),
                    'port': settings.get("channel_email_smtp_port", "587"),
                    'user': settings.get("channel_email_smtp_user"),
                    'password': settings.get("channel_email_smtp_pass"),
                    'from_address': settings.get("channel_email_from_address"),
                    'to_address': settings.get("channel_email_to_address")
                }
                adapters.append(EmailAdapter(smtp_config=smtp_config))
            except Exception as e:
                logger.error(f"Failed to initialize Email adapter: {e}")
        
        # 5. Messenger
        if settings.get("channel_messenger_enabled", "false") == "true":
            try:
                adapters.append(MessengerAdapter(
                    page_token=settings.get("channel_messenger_page_token"), 
                    verify_token=settings.get("channel_messenger_verify_token"),
                    app_secret=settings.get("channel_messenger_app_secret")
                ))
            except Exception as e:
                logger.error(f"Failed to initialize Messenger adapter: {e}")

        # 6. Google Chat
        if settings.get("channel_google_chat_enabled", "false") == "true":
            try:
                adapters.append(GoogleChatAdapter(
                    webhook_url=settings.get("channel_google_chat_webhook_url")
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
