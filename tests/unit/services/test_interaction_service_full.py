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

def test_redis_pending_requests_coverage():
    from src.services.interaction_service import RedisPendingRequests
    import sys
    
    # Test initialization with pytest check patched by copying sys.modules without "pytest"
    mock_modules = dict(sys.modules)
    if "pytest" in mock_modules:
        del mock_modules["pytest"]
        
    # 2026-08-10: patch target moved to the shared pool accessor —
    # RedisPendingRequests no longer calls redis.from_url itself.
    # 2026-08-10：patch 目標改為共用連線池存取函式。
    with patch('sys.modules', mock_modules), \
         patch('os.environ.get', return_value="redis://localhost:6379/0"), \
         patch('src.infrastructure.cache.redis_client.get_redis_sync') as mock_get_redis:
        mock_client = MagicMock()
        mock_get_redis.return_value = mock_client
        store2 = RedisPendingRequests()
        assert store2._redis is mock_client

    store = RedisPendingRequests()
    mock_redis = MagicMock()
    store._redis = mock_redis
    
    # 1. __setitem__
    req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C")
    store[req.request_id] = req
    mock_redis.set.assert_called_once()
    
    # 2. get / __getitem__ / __contains__
    mock_redis.get.return_value = '{"request_id": "' + req.request_id + '", "type": "APPROVAL", "title": "T", "content": "C", "status": "PENDING", "response": null, "payload": {}, "user_id": null, "expires_at": null, "channel_id": null}'
    retrieved = store[req.request_id]
    assert retrieved.request_id == req.request_id
    
    mock_redis.exists.return_value = True
    assert req.request_id in store
    
    # 3. __len__
    mock_redis.keys.return_value = ["interaction:123"]
    assert len(store) == 1
    
    # 4. keys / values
    assert store.keys() == ["123"]
    
    mock_redis.get.return_value = '{"request_id": "' + req.request_id + '", "type": "APPROVAL", "title": "T", "content": "C", "status": "PENDING", "response": null, "payload": {}, "user_id": null, "expires_at": null, "channel_id": null}'
    vals = store.values()
    assert len(vals) == 1
    
    # 5. pop
    popped = store.pop(req.request_id)
    assert popped.request_id == req.request_id
    mock_redis.delete.assert_called()
    
    # 6. clear
    store.clear()
    
    # 7. Test Exception fallback to None
    mock_redis.set.side_effect = Exception("Redis error")
    store[req.request_id] = req
    assert store._redis is None


# ──────────────────────────────────────────────────────────────────────
# 2026-07-14 (Loop 3): structured rejection-reason capture.
# ──────────────────────────────────────────────────────────────────────

from src.services.interaction_service import REJECTION_REASONS, _REJECTION_REASON_CODES


class TestRejectionFeedback:
    @pytest.mark.anyio
    async def test_reject_records_feedback_and_sends_reason_picker(self, mock_adapters, mock_classifier):
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")
        service._pending_requests[req.request_id] = req

        # user_id="u1" triggers dynamic per-user adapter resolution; force
        # it to fall back to the injected mock_adapters (matches how the
        # pre-existing tests in this file avoid pulling in a real adapter).
        with patch('src.infrastructure.channels.channel_factory.ChannelFactory.create_adapters', return_value=None), \
             patch.object(service, '_record_feedback') as mock_record:
            await service.handle_response(req.request_id, "reject")

        assert req.status == InteractionStatus.REJECTED
        mock_record.assert_called_once_with(req, "rejected")
        alert_calls = mock_adapters[0].send_alert.call_args_list
        assert len(alert_calls) == 1
        actions = alert_calls[0].kwargs["actions"]
        assert len(actions) == len(REJECTION_REASONS)
        assert all("action=reject_reason:" in a["data"] for a in actions)

    @pytest.mark.anyio
    async def test_approve_records_feedback_without_reason_picker(self, mock_adapters, mock_classifier):
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")
        service._pending_requests[req.request_id] = req

        with patch.object(service, '_record_feedback') as mock_record:
            await service.handle_response(req.request_id, "approve")

        mock_record.assert_called_once_with(req, "approved")
        mock_adapters[0].send_alert.assert_not_called()

    @pytest.mark.anyio
    async def test_reason_tap_updates_existing_row_and_acks(self, mock_adapters, mock_classifier):
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")
        req.status = InteractionStatus.REJECTED  # already rejected by a prior tap
        service._pending_requests[req.request_id] = req

        with patch.object(service, '_update_rejection_reason', return_value=True) as mock_update:
            await service.handle_response(req.request_id, "reject_reason:too_risky")

        mock_update.assert_called_once_with(req.request_id, "too_risky")
        mock_adapters[0].send_message.assert_called_once()

    @pytest.mark.anyio
    async def test_reason_tap_survives_already_rejected_status(self, mock_adapters, mock_classifier):
        """The is_pending() gate must not swallow the reason-picker follow-up
        just because the request is no longer PENDING (it's REJECTED by design
        at this point)."""
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")
        req.status = InteractionStatus.REJECTED
        service._pending_requests[req.request_id] = req
        assert req.is_pending() is False  # sanity: this is the trap the fix avoids

        with patch.object(service, '_update_rejection_reason', return_value=True):
            await service.handle_response(req.request_id, "reject_reason:bad_timing")

        mock_adapters[0].send_message.assert_called_once()

    @pytest.mark.anyio
    async def test_unknown_reason_code_rejected(self, mock_adapters, mock_classifier):
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")
        req.status = InteractionStatus.REJECTED
        service._pending_requests[req.request_id] = req

        with patch.object(service, '_update_rejection_reason') as mock_update:
            await service.handle_response(req.request_id, "reject_reason:not_a_real_code")

        mock_update.assert_not_called()
        mock_adapters[0].send_message.assert_not_called()

    def test_all_reason_codes_are_registered(self):
        assert _REJECTION_REASON_CODES == {code for code, _ in REJECTION_REASONS}
        assert "other" in _REJECTION_REASON_CODES


class TestFeedbackPersistence:
    def test_record_feedback_writes_expected_row(self):
        service = InteractionService(adapters=[], intent_classifier=None)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")

        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn

        with patch("src.data.database.get_db_engine", return_value=engine):
            service._record_feedback(req, "rejected", reason_code="too_risky")

        params = conn.execute.call_args[0][1]
        assert params["decision"] == "rejected"
        assert params["reason_code"] == "too_risky"
        assert params["uid"] == "u1"
        assert params["rid"] == req.request_id

    def test_record_feedback_swallows_db_errors(self):
        service = InteractionService(adapters=[], intent_classifier=None)
        req = InteractionRequest(type=InteractionType.APPROVAL, title="T", content="C", user_id="u1")

        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            service._record_feedback(req, "expired")  # must not raise

    def test_update_rejection_reason_only_targets_null_reason_rows(self):
        service = InteractionService(adapters=[], intent_classifier=None)
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.rowcount = 1
        engine.begin.return_value.__enter__.return_value = conn

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = service._update_rejection_reason("req-1", "wrong_ticker")

        assert result is True
        query_text = str(conn.execute.call_args[0][0])
        assert "reason_code IS NULL" in query_text
        assert "decision = 'rejected'" in query_text

    def test_update_rejection_reason_returns_false_when_no_match(self):
        service = InteractionService(adapters=[], intent_classifier=None)
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.rowcount = 0
        engine.begin.return_value.__enter__.return_value = conn

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = service._update_rejection_reason("req-1", "wrong_ticker")

        assert result is False


class TestExpiredFeedback:
    @pytest.mark.anyio
    async def test_timeout_records_expired_feedback(self, mock_adapters, mock_classifier):
        service = InteractionService(adapters=mock_adapters, intent_classifier=mock_classifier)

        with patch('time.time') as mock_time, \
             patch('asyncio.sleep', AsyncMock()), \
             patch.object(service, '_send_approval_request', AsyncMock()), \
             patch.object(service, '_record_feedback') as mock_record:

            times = [0, 1, 2]
            mock_time.side_effect = lambda: times.pop(0) if times else 999
            result = await service.request_approval("Title", "Content", timeout_seconds=10)

        assert result[1] == InteractionStatus.EXPIRED
        mock_record.assert_called_once()
        assert mock_record.call_args[0][1] == "expired"
