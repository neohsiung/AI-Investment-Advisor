import pytest
from unittest.mock import MagicMock, patch
import os
import sys

@pytest.fixture
def mock_sdk():
    # Mock linebot modules in sys.modules to prevent ImportError
    mock_linebot = MagicMock()
    mock_v3 = MagicMock()
    mock_messaging = MagicMock()
    mock_webhooks = MagicMock()
    mock_exceptions = MagicMock()
    
    # Setup hierarchy
    mock_linebot.v3 = mock_v3
    mock_v3.messaging = mock_messaging
    mock_v3.webhooks = mock_webhooks
    
    class MockInvalidSignatureError(Exception):
        pass

    mock_v3.exceptions = mock_exceptions
    mock_exceptions.InvalidSignatureError = MockInvalidSignatureError

    
    # Setup classes
    mock_messaging.Configuration = MagicMock()
    mock_messaging.ApiClient = MagicMock()
    mock_messaging.MessagingApi = MagicMock()
    mock_messaging.PushMessageRequest = MagicMock()
    mock_messaging.FlexMessage = MagicMock()
    mock_messaging.TextMessageContent = MagicMock()
    
    mock_v3.WebhookHandler = MagicMock()
    mock_webhooks.MessageEvent = MagicMock()
    mock_webhooks.PostbackEvent = MagicMock()
    
    # Apply patches to sys.modules
    with patch.dict(sys.modules, {
        'linebot': mock_linebot,
        'linebot.v3': mock_v3,
        'linebot.v3.messaging': mock_messaging,
        'linebot.v3.webhooks': mock_webhooks,
        'linebot.v3.exceptions': mock_exceptions
    }):
        # Import/Reload subject
        import src.infrastructure.channels.line_adapter
        import importlib
        importlib.reload(src.infrastructure.channels.line_adapter)
        
        # Patch env vars
        with patch.dict('os.environ', {
            'LINE_CHANNEL_ACCESS_TOKEN': 'test_token',
            'LINE_CHANNEL_SECRET': 'test_secret'
        }):
            yield {
                'msg_api': mock_messaging.MessagingApi.return_value,
                'handler': mock_v3.WebhookHandler.return_value,
                'adapter_class': src.infrastructure.channels.line_adapter.LineBotAdapter,
                'subject': src.infrastructure.channels.line_adapter
            }

def test_line_adapter_init(mock_sdk):
    """Test initialization with SDK present."""
    LineBotAdapter = mock_sdk['adapter_class']
    adapter = LineBotAdapter()
    assert adapter.is_active is True
    assert adapter.messaging_api is not None

def test_line_adapter_mock_mode(mock_sdk):
    """Test fallback when SDK missing or token missing."""
    subject = mock_sdk['subject']
    LineBotAdapter = mock_sdk['adapter_class']
    
    # Force HAS_LINE_SDK to False
    orig = subject.HAS_LINE_SDK
    subject.HAS_LINE_SDK = False
    try:
        adapter = LineBotAdapter()
        assert adapter.is_active is False
        # Verify send doesn't crash
        adapter.send_flex_alert("u1", "Title", "Content")
    finally:
        subject.HAS_LINE_SDK = orig

def test_send_flex_alert(mock_sdk):
    """Test sending logic."""
    LineBotAdapter = mock_sdk['adapter_class']
    adapter = LineBotAdapter()
    adapter.messaging_api.push_message = MagicMock()
    
    actions = [{"label": "Buy", "data": "action=buy"}]
    adapter.send_flex_alert("u1", "Alert Title", "Main Content", actions)
    
    # Verify push_message call
    adapter.messaging_api.push_message.assert_called_once()
    
    # Verify logic
    call_args = adapter.messaging_api.push_message.call_args
    request = call_args[0][0]
    # Simple check that it's a request object
    assert request is not None

def test_handle_webhook(mock_sdk):
    """Test webhook logic."""
    LineBotAdapter = mock_sdk['adapter_class']
    adapter = LineBotAdapter()
    
    # Setup mock parser
    mock_parser = MagicMock()
    mock_parser.parse.return_value = []
    
    # Attach parser to handler instance
    adapter.handler.parser = mock_parser
    
    # New signature: payload, headers dict
    adapter.handle_webhook("body", {"X-Line-Signature": "sig"})
    
    # Assert parser.parse is called
    mock_parser.parse.assert_called_with("body", "sig")

def test_handle_webhook_inactive(mock_sdk):
    subject = mock_sdk['subject']
    LineBotAdapter = mock_sdk['adapter_class']
    
    orig = subject.HAS_LINE_SDK
    subject.HAS_LINE_SDK = False
    try:
        adapter = LineBotAdapter()
        # Should do nothing
        adapter.handle_webhook("body", "sig")
    finally:
        subject.HAS_LINE_SDK = orig


