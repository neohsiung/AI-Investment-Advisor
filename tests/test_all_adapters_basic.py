import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.channels.slack_adapter import SlackAdapter
from src.infrastructure.channels.telegram_adapter import TelegramAdapter
from src.infrastructure.channels.messenger_adapter import MessengerAdapter
from src.infrastructure.channels.google_chat_adapter import GoogleChatAdapter

@pytest.mark.parametrize("adapter_class,env_key", [
    (SlackAdapter, "SLACK_BOT_TOKEN"),
    (TelegramAdapter, "TELEGRAM_BOT_TOKEN"),
    (MessengerAdapter, "MESSENGER_PAGE_TOKEN"),
    (GoogleChatAdapter, "GOOGLE_CHAT_WEBHOOK_URL")
])
def test_adapter_basic_flow(adapter_class, env_key):
    with patch.dict('os.environ', {env_key: "fake_token", "SLACK_CHANNEL_ID": "c1", "TELEGRAM_CHAT_ID": "t1"}):
        adapter = adapter_class()
        assert adapter.is_active is True
        
        # Test register
        cb = MagicMock()
        adapter.register_callback(cb)
        
        # Test handle_webhook (Internal)
        # For simple adapters, it should mostly return something or at least not crash
        res = adapter.handle_webhook({"type": "test"}, {"header": "val"})
        assert res is not None

def test_slack_adapter_specifics():
    with patch.dict('os.environ', {"SLACK_BOT_TOKEN": "fake", "SLACK_CHANNEL_ID": "c1"}):
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            adapter = SlackAdapter()
            adapter.send_alert("user", "Title", "Body")
            mock_post.assert_called_once()

def test_telegram_adapter_specifics():
    with patch.dict('os.environ', {"TELEGRAM_BOT_TOKEN": "fake", "TELEGRAM_CHAT_ID": "t1"}):
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            adapter = TelegramAdapter()
            adapter.send_alert("user", "Title", "Body")
            mock_post.assert_called_once()
