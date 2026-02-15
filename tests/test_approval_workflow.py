import pytest
from unittest.mock import MagicMock, patch
import time
import threading
from src.services.interaction_service import InteractionService, InteractionStatus
from src.domain.interaction import InteractionRequest, InteractionType
from src.infrastructure.channels.line_adapter import LineBotAdapter

class TestApprovalWorkflow:
    
    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock(spec=LineBotAdapter)
        # Verify register_callback is called
        return adapter

    def test_interaction_request_flow(self, mock_adapter):
        """
        Verify that request_approval sends a message and waits for response.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        # We need to simulate the user response in a separate thread 
        # because request_approval is blocking.
        
        request_id_container = {}
        
        def simulate_user_response():
            time.sleep(1) # Wait for request to be registered
            # Find the pending request
            if not service._pending_requests:
                return
            
            req_id = list(service._pending_requests.keys())[0]
            request_id_container['id'] = req_id
            
            # Simulate Webhook Callback (Approve)
            service.handle_response(req_id, "approve")
            
        thread = threading.Thread(target=simulate_user_response)
        thread.start()
        
        # Blocking Call
        result = service.request_approval(
            title="Test Approval",
            content="Approve this?",
            timeout_seconds=5
        )
        
        thread.join()
        
        assert result is True
        assert service._pending_requests[request_id_container['id']].status == InteractionStatus.APPROVED
        
        # Verify Adapter call
        mock_adapter.send_alert.assert_called_once()
        args, kwargs = mock_adapter.send_alert.call_args
        assert "Approve this?" in kwargs['content']
        assert len(kwargs['actions']) == 2 # Approve, Reject

    def test_interaction_timeout(self, mock_adapter):
        """
        Verify timeout behavior.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        # Blocking Call with short timeout
        start = time.time()
        result = service.request_approval(
            title="Timeout Test",
            content="...",
            timeout_seconds=1
        )
        duration = time.time() - start
        
        assert result is False
        assert duration >= 1.0

    def test_interaction_rejection(self, mock_adapter):
        """
        Verify rejection flow.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        def simulate_reject():
            time.sleep(1)
            if not service._pending_requests: return
            req_id = list(service._pending_requests.keys())[0]
            service.handle_response(req_id, "reject")
            
        thread = threading.Thread(target=simulate_reject)
        thread.start()
        
        result = service.request_approval(
            title="Reject Test", 
            content="...",
            timeout_seconds=5
        )
        thread.join()
        
        assert result is False
