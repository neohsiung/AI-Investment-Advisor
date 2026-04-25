import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.council_adapter import CouncilAgentAdapter

@pytest.mark.asyncio
async def test_council_adapter_run_sync_loop():
    """Test adapter runs via async run() which delegates to CouncilService."""
    with patch('src.agents.council_adapter.CouncilService') as MockService:
        mock_instance = MagicMock()
        MockService.return_value = mock_instance
        
        # start_session is async, so mock with AsyncMock
        mock_instance.start_session = AsyncMock(return_value={"result": "success"})
        
        adapter = CouncilAgentAdapter(user_id="test_user", scope="test", topic="Test Topic")
        result = await adapter.run({"user_id": "test_user"})
        
        assert result["result"] == "success"
        mock_instance.start_session.assert_called_with(
            topic="Test Topic",
            context_data={"user_id": "test_user"},
            user_id="test_user",
            scope="test"
        )

@pytest.mark.asyncio
async def test_council_adapter_run_async_loop_running():
    """Test adapter when called in an async context (most common case)."""
    with patch('src.agents.council_adapter.CouncilService') as MockService:
        mock_instance = MagicMock()
        MockService.return_value = mock_instance
        
        mock_instance.start_session = AsyncMock(return_value={"result": "threaded"})
        
        adapter = CouncilAgentAdapter(user_id="test_user")
        result = await adapter.run({"user_id": "test_user"})
        
        assert result["result"] == "threaded"
        assert mock_instance.start_session.called
