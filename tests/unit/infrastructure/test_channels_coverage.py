import pytest
import asyncio
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from unittest.mock import MagicMock, patch
from src.infrastructure.channels.channel_factory import ChannelFactory
from src.infrastructure.channels.base_adapter import BaseChannelAdapter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

class TestChannelFactory:
    def test_create_adapters_all_enabled(self):
        settings = {
            "channel_line_enabled": "true",
            "channel_slack_enabled": "true",
            "channel_telegram_enabled": "true",
            "channel_email_enabled": "true",
            "channel_messenger_enabled": "true",
            "channel_google_chat_enabled": "true",
            "channel_email_smtp_server": "smtp.test.com",
            # other settings can be blank for basic init
        }
        
        with patch('src.infrastructure.channels.line_adapter.LineBotAdapter'), \
             patch('src.infrastructure.channels.slack_adapter.SlackAdapter'), \
             patch('src.infrastructure.channels.telegram_adapter.TelegramAdapter'), \
             patch('src.infrastructure.channels.messenger_adapter.MessengerAdapter'), \
             patch('src.infrastructure.channels.google_chat_adapter.GoogleChatAdapter'), \
             patch('src.infrastructure.channels.email_adapter.EmailAdapter'):
            
            adapters = ChannelFactory.create_adapters(settings)
            # 6 enabled + 1 WebAdapter (always included) = 7
            assert len(adapters) == 7

    def test_create_adapters_error_handling(self):
        settings = {"channel_line_enabled": "true"}
        with patch('src.infrastructure.channels.line_adapter.LineBotAdapter', side_effect=Exception("Init Fail")):
            adapters = ChannelFactory.create_adapters(settings)
            # Should not include LINE, but always includes WebAdapter
            assert len(adapters) >= 1
            assert not any(isinstance(a, MagicMock) for a in adapters)

class TestBaseChannelAdapter:
    def test_init_and_callbacks(self):
        adapter = BaseChannelAdapter(default_target_id="default_id")
        assert adapter.default_target_id == "default_id"
        
        callback = MagicMock()
        adapter.register_callback(callback)
        assert adapter.callback == callback
        
        text_callback = MagicMock()
        adapter.register_text_callback(text_callback)
        assert adapter.text_callback == text_callback

    def test_resolve_target_id(self) -> None:
        adapter = BaseChannelAdapter(default_target_id="default_id")
        
        assert adapter._resolve_target_id("user@test.com") == "default_id"
        assert adapter._resolve_target_id("system") == "default_id"
        assert adapter._resolve_target_id("broadcast") == "default_id"
        assert adapter._resolve_target_id("") == "default_id"
        assert adapter._resolve_target_id("specific_id") == "specific_id"

    @pytest.mark.anyio
    async def test_trigger_callbacks(self):
        adapter = BaseChannelAdapter()
        
        # Test sync callback
        sync_cb = MagicMock()
        adapter.register_callback(sync_cb)
        await adapter._trigger_callback("req1", "action1")
        sync_cb.assert_called_with("req1", "action1")
        
        # Test async callback
        async_cb = MagicMock(side_effect=lambda r, a: asyncio.Future())
        # Actually needs to be a coroutine function
        async def mock_async_cb(r, a):
            pass
        
        adapter.register_callback(mock_async_cb)
        await adapter._trigger_callback("req2", "action2")
        
    @pytest.mark.anyio
    async def test_trigger_text_callbacks(self):
        adapter = BaseChannelAdapter()
        
        async def mock_async_text_cb(adapter_inst, user, text):
            pass
            
        adapter.register_text_callback(mock_async_text_cb)
        await adapter._trigger_text_callback("user1", "hello")

    @pytest.mark.anyio
    async def test_stubs(self):
        adapter = BaseChannelAdapter()
        assert await adapter.send_message("u", "m") is False
        assert await adapter.receive_command("p") is None
        assert await adapter.authenticate("r") is True
        assert await adapter.send_alert("u", "t", "c") is False
        assert await adapter.handle_webhook("p") == {"ok": True}
        assert adapter.verify_signature("p") is True
