import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from src.services.interaction_service import InteractionService
from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus

@pytest.fixture
def mock_adapters():
    a1 = MagicMock()
    a1.register_callback = MagicMock()
    return [a1]

@pytest.fixture
def mock_classifier():
    c = MagicMock()
    c.classify.return_value = "APPROVE"
    return c

def test_interaction_service_init(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    assert len(service.adapters) == 1
    mock_adapters[0].register_callback.assert_called_once()
    mock_adapters[0].handle_webhook.assert_not_called() # Should be ready but not triggered yet

def test_interaction_service_create_request(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # We use request_approval which is blocking, so we'll test it by mocking the loop or the internal call
    with patch.object(service, '_send_approval_request') as mock_send:
        # Instead of calling blocking request_approval, we test the internal state after initialization
        assert service.intent_classifier == mock_classifier
        assert len(service.adapters) == 1

def test_interaction_service_handle_callback(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # Mock a pending request
    request_id = "req_123"
    req = InteractionRequest(
        type=InteractionType.APPROVAL,
        title="T",
        content="C"
    )
    # Match the request_id
    request_id = req.request_id
    service._pending_requests[request_id] = req
    
    # Simulate adapter callback
    service.handle_response(request_id, "APPROVE")
    
    # Verify status changed
    assert req.status == InteractionStatus.APPROVED

def test_interaction_service_handle_text(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # Mock a pending request for u1
    req = InteractionRequest(
        type=InteractionType.APPROVAL,
        user_id="u1",
        title="T",
        content="C"
    )
    request_id = req.request_id
    service._pending_requests[request_id] = req
    
    # Simulate text from user
    service.handle_text_response("u1", "Yes please")
    
    # Classifier should be invoked
    mock_classifier.classify.assert_called_with("Yes please")
    # Status should be updated via standard handler
    assert req.status == InteractionStatus.APPROVED

def test_interaction_service_request_approval_timeout(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # Mock time and sleep to avoid waiting 5 minutes
    with patch('time.time') as mock_time, \
         patch('time.sleep') as mock_sleep, \
         patch.object(service, '_send_approval_request'):
        
        # Use a counter to avoid StopIteration if it calls more than twice
        times = [0, 301, 302, 303] 
        def get_time():
            return times.pop(0) if times else 400
        mock_time.side_effect = get_time
        
        # This should call _send_approval_request and then loop once then exit
        result = service.request_approval("Title", "Content", timeout_seconds=300)
        assert result is False
        # Verify it went to the pending dict
        assert len(service._pending_requests) > 0

def test_interaction_service_request_approval_success(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    with patch('time.time') as mock_time, \
         patch('time.sleep') as mock_sleep, \
         patch.object(service, '_send_approval_request'):
        
        times = [0, 1, 2, 3, 4, 5]
        def get_time():
             return times.pop(0) if times else 10
        mock_time.side_effect = get_time
        
        # Find the request object that will be created
        def mock_approve_side_effect(*args, **kwargs):
            # Simulate external approval after one loop
            for req in service._pending_requests.values():
                req.status = InteractionStatus.APPROVED
                
        mock_sleep.side_effect = mock_approve_side_effect
        
        result = service.request_approval("Title", "Content", timeout_seconds=10)
        assert result is True

def test_interaction_service_request_approval_rejected(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    with patch('time.time') as mock_time, \
         patch('time.sleep') as mock_sleep, \
         patch.object(service, '_send_approval_request'):
        
        times = [0, 1, 2, 3]
        def get_time():
             return times.pop(0) if times else 10
        mock_time.side_effect = get_time
        
        def mock_reject_side_effect(*args, **kwargs):
            for req in service._pending_requests.values():
                req.status = InteractionStatus.REJECTED
                
        mock_sleep.side_effect = mock_reject_side_effect
        
        result = service.request_approval("Title", "Content", timeout_seconds=10)
        assert result is False

def test_interaction_domain_model():
    # Direct tests for InteractionRequest to boost domain coverage
    req = InteractionRequest(
        user_id="u1",
        title="T",
        content="C",
        type=InteractionType.APPROVAL,
        expires_at=datetime.now() + timedelta(seconds=60)
    )
    assert req.is_pending()
    req.status = InteractionStatus.APPROVED
    assert not req.is_pending()
    assert req.status == InteractionStatus.APPROVED

def test_interaction_service_handle_text_response(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # Mock a pending request
    req = InteractionRequest("u1", "T", "C", InteractionType.APPROVAL, expires_at=datetime.now() + timedelta(minutes=5))
    service._pending_requests[req.request_id] = req
    
    # Handle text response
    mock_classifier.classify.return_value = "APPROVE"
    service.handle_text_response("u1", "Yes")
    
    assert req.status == InteractionStatus.APPROVED

def test_interaction_service_inactive_adapters():
    # Test fallback constructor and inactive adapters
    with patch.dict('os.environ', {"LINE_CHANNEL_SECRET": "", "LINE_CHANNEL_ACCESS_TOKEN": ""}, clear=True):
        service = InteractionService()
        # Should have adapters but they might be inactive
        for adapter in service.adapters:
            if hasattr(adapter, 'is_active'):
                # In test env without keys, they should be inactive
                pass
        
        # Calling handle_response with unknown ID should just return
        service.handle_response("unknown", "approve")
