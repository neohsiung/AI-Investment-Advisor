import pytest
from unittest.mock import MagicMock, patch
import os
from src.infrastructure.channels.line_adapter import LineBotAdapter

@pytest.fixture
def mock_sdk():
    # Create valid mock classes
    class MockConfig:
        def __init__(self, access_token=None): pass
    class MockApiClient:
        def __init__(self, config=None): pass
    class MockMsgApi:
        def __init__(self, client=None): pass
        def push_message(self, req): pass
    class MockHandler:
        def __init__(self, secret=None): pass
        def handle(self, body, sig): pass

    # Patch module attributes
    with patch('src.infrastructure.channels.line_adapter.HAS_LINE_SDK', True), \
         patch('src.infrastructure.channels.line_adapter.Configuration', MockConfig, create=True), \
         patch('src.infrastructure.channels.line_adapter.ApiClient', MockApiClient, create=True), \
         patch('src.infrastructure.channels.line_adapter.MessagingApi', MockMsgApi, create=True), \
         patch('src.infrastructure.channels.line_adapter.WebhookHandler', MockHandler, create=True), \
         patch('src.infrastructure.channels.line_adapter.PushMessageRequest', MagicMock(), create=True), \
         patch('src.infrastructure.channels.line_adapter.FlexMessage', MagicMock(), create=True), \
         patch('src.infrastructure.channels.line_adapter.TextMessage', MagicMock(), create=True):
        
        # We need to capture the instance created inside __init__
        # Or simpler: we can just use MagicMock for the classes so we can inspect calls
        # Let's use patch with MagicMock, ensuring create=True
        pass

    # Actually, proper way is to patch where it's used.
    # But since the module might not have these names, we must set them on the module object.
    import src.infrastructure.channels.line_adapter as subject
    
    orig_attrs = {}
    attrs = {
        'Configuration': MagicMock(),
        'ApiClient': MagicMock(),
        'MessagingApi': MagicMock(),
        'WebhookHandler': MagicMock(),
        'PushMessageRequest': MagicMock(),
        'FlexMessage': MagicMock(),
        'TextMessage': MagicMock()
    }
    
    for k, v in attrs.items():
        if hasattr(subject, k):
            orig_attrs[k] = getattr(subject, k)
        setattr(subject, k, v)
    
    # Also patch HAS_LINE_SDK
    orig_has = subject.HAS_LINE_SDK
    subject.HAS_LINE_SDK = True
    
    # Also env vars
    with patch.dict('os.environ', {
        'LINE_CHANNEL_ACCESS_TOKEN': 'test_token',
        'LINE_CHANNEL_SECRET': 'test_secret'
    }):
        yield {
            'msg_api': attrs['MessagingApi'].return_value,
            'handler': attrs['WebhookHandler'].return_value
        }
    
    # Cleanup
    subject.HAS_LINE_SDK = orig_has
    for k in attrs:
        if k in orig_attrs:
            setattr(subject, k, orig_attrs[k])
        else:
            delattr(subject, k)

def test_line_adapter_init(mock_sdk):
    """Test initialization with SDK present."""
    adapter = LineBotAdapter()
    assert adapter.is_active is True
    assert adapter.messaging_api is not None

def test_line_adapter_mock_mode():
    """Test fallback when SDK missing or token missing."""
    with patch('src.infrastructure.channels.line_adapter.HAS_LINE_SDK', False):
        adapter = LineBotAdapter()
        assert adapter.is_active is False
        
        # Verify send doesn't crash
        adapter.send_flex_alert("u1", "Title", "Content")

def test_send_flex_alert(mock_sdk):
    """Test sending logic."""
    adapter = LineBotAdapter()
    
    actions = [{"label": "Buy", "data": "action=buy"}]
    adapter.send_flex_alert("u1", "Alert Title", "Main Content", actions)
    
    # Verify push_message call
    mock_sdk['msg_api'].push_message.assert_called_once()
    
    # Inspect arguments passed to PushMessageRequest constructor
    import src.infrastructure.channels.line_adapter as subject
    subject.PushMessageRequest.assert_called_once()
    call_args = subject.PushMessageRequest.call_args
    assert call_args.kwargs['to'] == 'u1'
    
    # Inspect arguments passed to push_message
    mock_sdk['msg_api'].push_message.assert_called_once()
    # The argument to push_message is the result of PushMessageRequest(...)
    # We can verify it is the return value of the class mock
    msg_arg = mock_sdk['msg_api'].push_message.call_args[0][0]
    assert msg_arg == subject.PushMessageRequest.return_value

def test_handle_webhook(mock_sdk):
    """Test webhook logic."""
    adapter = LineBotAdapter()
    adapter.handle_webhook("body", "sig")
    
    mock_sdk['handler'].handle.assert_called_with("body", "sig")

def test_handle_webhook_inactive():
    with patch('src.infrastructure.channels.line_adapter.HAS_LINE_SDK', False):
        adapter = LineBotAdapter()
        # Should do nothing
        adapter.handle_webhook("body", "sig")
