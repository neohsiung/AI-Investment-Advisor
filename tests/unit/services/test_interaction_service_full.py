import pytest
from datetime import datetime, timedelta
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.interaction_service import InteractionService
from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def mock_adapters():
    a1 = MagicMock()
    a1.register_callback = MagicMock()
    a1.send_alert = AsyncMock(return_value=True)
    a1.send_message = AsyncMock(return_value=True)
    a1._trigger_callback = AsyncMock(return_value=True)
    return [a1]

@pytest.fixture
def mock_classifier():
    c = MagicMock()
    c.classify.return_value = "APPROVE"
    return c

@pytest.fixture
def mock_settings():
    s = MagicMock()
    # Mock find_user_by_channel_id to return the same ID for tests
    s.find_user_by_channel_id.side_effect = lambda x: x
    return s

def test_interaction_service_init(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    assert len(service.adapters) == 1
    mock_adapters[0].register_callback.assert_called_once()

@pytest.mark.anyio
async def test_interaction_service_handle_callback(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    # Mock a pending request
    req = InteractionRequest(
        type=InteractionType.APPROVAL,
        title="T",
        content="C"
    )
    request_id = req.request_id
    service._pending_requests[request_id] = req
    
    # Simulate adapter callback
    await service.handle_response(request_id, "APPROVE")
    
    # Verify status changed
    assert req.status == InteractionStatus.APPROVED
    # Verify feedback sent
    mock_adapters[0].send_message.assert_called()

@pytest.mark.anyio
async def test_interaction_service_handle_text(mock_adapters, mock_classifier, mock_settings):
    service = InteractionService(
        adapters=mock_adapters, 
        intent_classifier=mock_classifier,
        settings_service=mock_settings
    )
    
    # Mock a pending request for u1
    req = InteractionRequest(
        type=InteractionType.APPROVAL,
        user_id="u1",
        title="T",
        content="C"
    )
    request_id = req.request_id
    service._pending_requests[request_id] = req
    
    # Mock trigger_callback to simulate what a real adapter does
    async def mock_trigger(req_id, intent_type):
        await service.handle_response(req_id, intent_type)
    mock_adapters[0]._trigger_callback = AsyncMock(side_effect=mock_trigger)
    
    # Simulate text from user with VerificationService patched
    with patch('src.services.verification_service.VerificationService') as mock_vs:
        mock_vs.return_value.verify_any_reply = AsyncMock(return_value=False)
        await service.handle_text_response(mock_adapters[0], "u1", "Yes please")
    
    # Classifier should be invoked
    mock_classifier.classify.assert_called_with("Yes please")
    # Status should be updated via standard handler
    assert req.status == InteractionStatus.APPROVED

@pytest.mark.anyio
async def test_interaction_service_request_approval_timeout(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    with patch('time.time') as mock_time, \
         patch('asyncio.sleep', AsyncMock()) as mock_sleep, \
         patch.object(service, '_send_approval_request', AsyncMock()):
        
        # Use a counter to avoid StopIteration
        times = [0, 301, 302, 303] 
        def get_time():
            return times.pop(0) if times else 400
        mock_time.side_effect = get_time
        
        result = await service.request_approval("Title", "Content", timeout_seconds=300)
        assert result[0] is False
        assert len(service._pending_requests) > 0

@pytest.mark.anyio
async def test_interaction_service_request_approval_success(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    with patch('time.time') as mock_time, \
         patch('asyncio.sleep', AsyncMock()) as mock_sleep, \
         patch.object(service, '_send_approval_request', AsyncMock()):
        
        times = [0, 1, 2, 3, 4, 5]
        def get_time():
             return times.pop(0) if times else 10
        mock_time.side_effect = get_time
        
        # Find the request object that will be created
        async def mock_approve_side_effect(*args, **kwargs):
            # Simulate external approval after one loop
            for req in service._pending_requests.values():
                req.status = InteractionStatus.APPROVED
                
        mock_sleep.side_effect = mock_approve_side_effect
        
        result = await service.request_approval("Title", "Content", timeout_seconds=10)
        assert result[0] is True

@pytest.mark.anyio
async def test_interaction_service_request_approval_rejected(mock_adapters, mock_classifier):
    service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
    
    with patch('time.time') as mock_time, \
         patch('asyncio.sleep', AsyncMock()) as mock_sleep, \
         patch.object(service, '_send_approval_request', AsyncMock()):
        
        times = [0, 1, 2, 3]
        def get_time():
             return times.pop(0) if times else 10
        mock_time.side_effect = get_time
        
        async def mock_reject_side_effect(*args, **kwargs):
            for req in service._pending_requests.values():
                req.status = InteractionStatus.REJECTED
                
        mock_sleep.side_effect = mock_reject_side_effect
        
        result = await service.request_approval("Title", "Content", timeout_seconds=10)
        assert result[0] is False

def test_interaction_domain_model():
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

@pytest.mark.anyio
async def test_interaction_service_handle_text_response_intent(mock_adapters, mock_classifier, mock_settings):
    service = InteractionService(
        adapters=mock_adapters, 
        intent_classifier=mock_classifier,
        settings_service=mock_settings
    )
    
    req = InteractionRequest("u1", "T", "C", InteractionType.APPROVAL, expires_at=datetime.now() + timedelta(minutes=5))
    service._pending_requests[req.request_id] = req
    
    mock_classifier.classify.return_value = "APPROVE"
    
    async def mock_trigger(req_id, intent_type):
        await service.handle_response(req_id, intent_type)
    mock_adapters[0]._trigger_callback = AsyncMock(side_effect=mock_trigger)
    
    with patch('src.services.verification_service.VerificationService') as mock_vs:
        mock_vs.return_value.verify_any_reply = AsyncMock(return_value=False)
        await service.handle_text_response(mock_adapters[0], "u1", "Yes")
    
    assert req.status == InteractionStatus.APPROVED

@pytest.mark.anyio
async def test_interaction_service_inactive_adapters():
    with patch.dict('os.environ', {"LINE_CHANNEL_SECRET": "", "LINE_CHANNEL_ACCESS_TOKEN": ""}, clear=True):
        service = InteractionService()
        await service.handle_response("unknown", "approve")
