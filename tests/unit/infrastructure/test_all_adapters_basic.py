import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from src.infrastructure.channels.slack_adapter import SlackAdapter
from src.infrastructure.channels.telegram_adapter import TelegramAdapter
from src.infrastructure.channels.messenger_adapter import MessengerAdapter
from src.infrastructure.channels.google_chat_adapter import GoogleChatAdapter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
@pytest.mark.parametrize("adapter_class,env_key", [
    (SlackAdapter, "SLACK_BOT_TOKEN"),
    (TelegramAdapter, "TELEGRAM_BOT_TOKEN"),
    (MessengerAdapter, "MESSENGER_PAGE_TOKEN"),
    (GoogleChatAdapter, "GOOGLE_CHAT_WEBHOOK_URL")
])
async def test_adapter_basic_flow(adapter_class, env_key):
    with patch.dict('os.environ', {env_key: "fake_token", "SLACK_CHANNEL_ID": "c1", "TELEGRAM_CHAT_ID": "t1"}):
        adapter = adapter_class()
        assert adapter.is_active is True

@pytest.mark.anyio
async def test_slack_adapter_specifics():
    with patch.dict('os.environ', {"SLACK_BOT_TOKEN": "fake", "SLACK_CHANNEL_ID": "c1"}):
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
            adapter = SlackAdapter()
            result = await adapter.send_alert("user", "Title", "Body")
            assert result is True
            assert mock_post.called

@pytest.mark.anyio
async def test_telegram_adapter_specifics():
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True})
        )
        # Provide credentials via constructor so DB lookup is skipped as fallback
        adapter = TelegramAdapter(bot_token="fake_token", chat_id="t1")
        result = await adapter.send_alert("user", "Title", "Body")
        assert result is True
        assert mock_post.called
