import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.channels.channel_factory import ChannelFactory

def test_parse_setting():
    assert ChannelFactory._parse_setting("true") is True
    assert ChannelFactory._parse_setting("false") is False
    assert ChannelFactory._parse_setting('"hello"') == "hello"
    assert ChannelFactory._parse_setting("123") == 123
    assert ChannelFactory._parse_setting(None) is None
    assert ChannelFactory._parse_setting(42) == 42

def test_create_adapters_none_enabled():
    settings = {}
    adapters = ChannelFactory.create_adapters(settings)
    
    # Only WebAdapter should be present by default
    assert len(adapters) == 1
    from src.infrastructure.channels.web_adapter import WebAdapter
    assert isinstance(adapters[0], WebAdapter)

def test_create_adapters_all_enabled():
    settings = {
        "channel_line_enabled": "true",
        "channel_line_access_token": "token",
        "channel_slack_enabled": "true",
        "channel_telegram_enabled": "true",
        "channel_email_enabled": "true",
        "channel_messenger_enabled": "true",
        "channel_google_chat_enabled": "true"
    }
    
    with patch('src.infrastructure.channels.channel_factory.LineBotAdapter'), \
         patch('src.infrastructure.channels.channel_factory.SlackAdapter'), \
         patch('src.infrastructure.channels.channel_factory.TelegramAdapter'), \
         patch('src.infrastructure.channels.email_adapter.EmailAdapter'), \
         patch('src.infrastructure.channels.channel_factory.MessengerAdapter'), \
         patch('src.infrastructure.channels.channel_factory.GoogleChatAdapter'), \
         patch('src.infrastructure.channels.web_adapter.WebAdapter'):
        
        adapters = ChannelFactory.create_adapters(settings)
        
        # Line, Slack, Telegram, Email, Messenger, Google Chat, Web = 7
        assert len(adapters) == 7

def test_create_adapters_with_errors():
    settings = {
        "channel_line_enabled": "true"
    }
    
    # Mock LineBotAdapter to raise an exception
    with patch('src.infrastructure.channels.channel_factory.LineBotAdapter', side_effect=Exception("Init Error")):
        adapters = ChannelFactory.create_adapters(settings)
        
        # Only WebAdapter should succeed
        assert len(adapters) == 1
