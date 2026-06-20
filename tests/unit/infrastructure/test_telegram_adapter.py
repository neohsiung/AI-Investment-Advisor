import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import os
import json

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def mock_db():
    with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_pool_factory:
        mock_pool = MagicMock() # Use MagicMock for the pool itself
        mock_pool_factory.return_value = mock_pool
        
        mock_conn = AsyncMock()
        
        # Setup the async context manager for pool.acquire()
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool.acquire.return_value = mock_acquire
        
        yield {
            'pool_factory': mock_pool_factory,
            'pool': mock_pool,
            'conn': mock_conn
        }

@pytest.mark.anyio
async def test_telegram_adapter_get_settings(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    # Setup mock DB response
    mock_db['conn'].fetchval.side_effect = ["test_token", "test_chat_id"]
    
    token, chat_id = await adapter._get_user_telegram_settings("u123")
    
    assert token == "test_token"
    assert chat_id == "test_chat_id"
    assert mock_db['conn'].fetchval.call_count == 2

@pytest.mark.anyio
async def test_send_alert_success(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    # Setup mock DB response
    mock_db['conn'].fetchval.side_effect = ["test_token", "test_chat_id"]
    
    # Mock httpx
    with patch('httpx.AsyncClient', autospec=True) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        
        mock_client.post = AsyncMock(return_value=mock_response)
        
        success = await adapter.send_alert("u123", "Title", "Content **bold**")
        
        assert success is True
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        # The first arg to client.post(...) is the URL
        assert "api.telegram.org/bottest_token/sendMessage" in args[0]
        assert kwargs['json']['chat_id'] == "test_chat_id"
        assert "<b>bold</b>" in kwargs['json']['text']

@pytest.mark.anyio
async def test_send_alert_missing_settings(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    # Setup mock DB response (missing settings)
    mock_db['conn'].fetchval.return_value = None
    
    success = await adapter.send_alert("u123", "Title", "Content")
    
    assert success is False

@pytest.mark.anyio
async def test_send_alert_api_error(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    mock_db['conn'].fetchval.side_effect = ["token", "chat_id"]
    
    with patch('httpx.AsyncClient', autospec=True) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}
        
        mock_client.post = AsyncMock(return_value=mock_response)
        
        success = await adapter.send_alert("u123", "Title", "Content")
        
        assert success is False
        mock_client.post.assert_called_once()

@pytest.mark.anyio
async def test_send_alert_sync(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    mock_db['conn'].fetchval.side_effect = ["token", "chat_id"]
    
    with patch('httpx.AsyncClient', autospec=True) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Test sync call
        success = adapter.send_alert_sync("u123", "Title", "Content")
        
        assert success is True
        mock_client.post.assert_called_once()

@pytest.mark.anyio
async def test_handle_webhook_callback(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    # Setup mock callback
    mock_callback = AsyncMock()
    adapter.register_callback(mock_callback)
    
    payload = {
        "callback_query": {
            "id": "q123",
            "data": "id=req456&action=approve"
        }
    }
    
    await adapter.handle_webhook(payload)
    
    mock_callback.assert_called_once_with("req456", "approve")


@pytest.mark.anyio
async def test_send_alert_html_formatting(mock_db):
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    mock_db['conn'].fetchval.side_effect = ["test_token", "test_chat_id"]
    
    with patch('httpx.AsyncClient', autospec=True) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_client.post = AsyncMock(return_value=mock_response)
        
        html_content = """<!DOCTYPE html>
<html>
<body>
    <h1>Report Title</h1>
    <p>This is a <b>bold</b> statement with <a href="https://example.com">a link</a>.</p>
    <script>console.log("ignore me");</script>
</body>
</html>"""
        
        success = await adapter.send_alert("u123", "Title", html_content)
        
        assert success is True
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        text_payload = kwargs['json']['text']
        
        # Verify that allowed tags are preserved
        # 驗證允許的標記被保留
        assert "<b>bold</b>" in text_payload
        assert '<a href="https://example.com">a link</a>' in text_payload
        
        # Verify that script tag content and other disallowed tags are stripped/ignored
        # 驗證 script 標記內容與其他不允許的標記被剝離/忽略
        assert "console.log" not in text_payload
        assert "<html>" not in text_payload
        assert "<h1>" not in text_payload
        assert "Report Title" in text_payload
