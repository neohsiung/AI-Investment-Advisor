import pytest
from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus
from src.domain.interfaces import IChannelAdapter
from datetime import datetime, timedelta

def test_interaction_request_full_coverage():
    # Test all fields and methods of InteractionRequest
    expires = datetime.now() + timedelta(hours=1)
    req = InteractionRequest(
        user_id="u1",
        title="T",
        content="C",
        type=InteractionType.APPROVAL,
        expires_at=expires
    )
    
    assert req.user_id == "u1"
    assert req.title == "T"
    assert req.content == "C"
    assert req.type == InteractionType.APPROVAL
    assert req.expires_at == expires
    assert req.status == InteractionStatus.PENDING
    
    # Test is_pending
    assert req.is_pending() is True
    
    # Test expiration logic inside is_pending
    req.expires_at = datetime.now() - timedelta(seconds=1)
    assert req.is_pending() is False
    assert req.status == InteractionStatus.EXPIRED
    
    # Test Approve/Reject
    req2 = InteractionRequest("u2", "T", "C", InteractionType.APPROVAL)
    req2.status = InteractionStatus.APPROVED
    assert req2.status == InteractionStatus.APPROVED
    assert not req2.is_pending()

def test_channel_adapter_interface():
    # Sanity check for the interface (though it's abstract)
    class MockAdapter(IChannelAdapter):
        def send_alert(self, user_id, title, content, actions=None, **kwargs):
            return True
        def register_callback(self, callback_func):
            pass
        def register_text_callback(self, callback_func):
            pass
        def handle_webhook(self, payload, headers=None):
            return True
        @property
        def is_active(self):
            return True
            
    adapter = MockAdapter()
    assert adapter.send_alert("u", "t", "c") is True
    assert adapter.is_active is True
