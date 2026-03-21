import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import time
from src.services.interaction_service import InteractionService, InteractionStatus
from src.domain.interaction import InteractionRequest, InteractionType
from src.infrastructure.channels.line_adapter import LineBotAdapter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

class TestApprovalWorkflow:
    
    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock(spec=LineBotAdapter)
        adapter.send_alert = AsyncMock()
        adapter.send_message = AsyncMock()
        return adapter

    @pytest.mark.anyio
    async def test_interaction_request_flow(self, mock_adapter):
        """
        Verify that request_approval sends a message and waits for response.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        async def simulate_user_response():
            await asyncio.sleep(0.5) # Wait for request to be registered
            if not service._pending_requests:
                return
            
            req_id = list(service._pending_requests.keys())[0]
            # Simulate Webhook Callback (Approve)
            await service.handle_response(req_id, "approve")
            
        # Start simulation task
        task = asyncio.create_task(simulate_user_response())
        
        # Async Call
        result = await service.request_approval(
            title="Test Approval",
            content="Approve this?",
            timeout_seconds=5
        )
        
        await task
        
        assert result[0] is True
        req_id = list(service._pending_requests.keys())[0]
        assert service._pending_requests[req_id].status == InteractionStatus.APPROVED
        
        # Verify Adapter call
        mock_adapter.send_alert.assert_called_once()
        args, kwargs = mock_adapter.send_alert.call_args
        assert "Approve this?" in kwargs['content']

    @pytest.mark.anyio
    async def test_interaction_timeout(self, mock_adapter):
        """
        Verify timeout behavior.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        # Async Call with short timeout
        start = time.time()
        result = await service.request_approval(
            title="Timeout Test",
            content="...",
            timeout_seconds=1
        )
        duration = time.time() - start
        
        assert result[0] is False
        assert duration >= 1.0

    @pytest.mark.anyio
    async def test_interaction_rejection(self, mock_adapter):
        """
        Verify rejection flow.
        """
        service = InteractionService(adapters=[mock_adapter])
        
        async def simulate_reject():
            await asyncio.sleep(0.5)
            if not service._pending_requests: return
            req_id = list(service._pending_requests.keys())[0]
            await service.handle_response(req_id, "reject")
            
        task = asyncio.create_task(simulate_reject())
        
        result = await service.request_approval(
            title="Reject Test", 
            content="...",
            timeout_seconds=5
        )
        await task
        
        assert result[0] is False
