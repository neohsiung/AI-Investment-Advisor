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
        """
        adapters = []
        
        # 1. LINE
        if settings.get("channel_line_enabled", "false") == "true":
            try:
                line_token = settings.get("channel_line_access_token")
                line_secret = settings.get("channel_line_secret")
                # LineBotAdapter handles internal env fallback if None, but we pass what we have
                adapters.append(LineBotAdapter(channel_access_token=line_token, channel_secret=line_secret))
                logger.info("Channel: LINE enabled.")
            except Exception as e:
                logger.error(f"Failed to initialize LINE adapter: {e}")

        # 2. Slack
        if settings.get("channel_slack_enabled", "false") == "true":
            try:
                bot_token = settings.get("channel_slack_bot_token")
                channel_id = settings.get("channel_slack_channel_id")
                adapters.append(SlackAdapter(bot_token=bot_token, channel_id=channel_id))
                logger.info("Channel: Slack enabled.")
            except Exception as e:
                logger.error(f"Failed to initialize Slack adapter: {e}")

        # 3. Telegram
        if settings.get("channel_telegram_enabled", "false") == "true":
            try:
                bot_token = settings.get("channel_telegram_bot_token")
                chat_id = settings.get("channel_telegram_chat_id")
                adapters.append(TelegramAdapter(bot_token=bot_token, chat_id=chat_id))
                logger.info("Channel: Telegram enabled.")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram adapter: {e}")

        # 4. Messenger
        if settings.get("channel_messenger_enabled", "false") == "true":
            try:
                page_token = settings.get("channel_messenger_page_token")
                verify_token = settings.get("channel_messenger_verify_token")
                adapters.append(MessengerAdapter(page_token=page_token, verify_token=verify_token))
                logger.info("Channel: Messenger enabled.")
            except Exception as e:
                logger.error(f"Failed to initialize Messenger adapter: {e}")

        # 5. Google Chat
        if settings.get("channel_google_chat_enabled", "false") == "true":
            try:
                webhook_url = settings.get("channel_google_chat_webhook_url")
                adapters.append(GoogleChatAdapter(webhook_url=webhook_url))
                logger.info("Channel: Google Chat enabled.")
            except Exception as e:
                logger.error(f"Failed to initialize Google Chat adapter: {e}")

        return adapters
