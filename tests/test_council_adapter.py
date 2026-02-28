import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.agents.council_adapter import CouncilAgentAdapter

def test_council_adapter_run_sync_loop():
    """Test adapter when no loop is running."""
    with patch('src.agents.council_adapter.CouncilService') as MockService, \
         patch('src.agents.council_adapter.asyncio') as mock_asyncio:
        
        mock_instance = MagicMock()
        MockService.return_value = mock_instance
        
        # Mock loop
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_asyncio.get_event_loop.return_value = mock_loop
        # Support fallback to new_event_loop if get raises
        
        adapter = CouncilAgentAdapter(scope="test", topic="Test Topic")
        
        # run_until_complete needs to return what start_session returns (a coroutine object)
        mock_coro = MagicMock()
        mock_instance.start_session.return_value = mock_coro
        mock_loop.run_until_complete.return_value = {"result": "success"}
        
        result = adapter.run({})
        
        assert result["result"] == "success"
        mock_instance.start_session.assert_called_with("Test Topic", {}, "test", user_id='system')
        mock_loop.run_until_complete.assert_called_with(mock_coro)

def test_council_adapter_run_async_loop_running():
    """Test adapter when loop IS running (needs thread/executor)."""
    with patch('src.agents.council_adapter.CouncilService') as MockService, \
         patch('src.agents.council_adapter.asyncio') as mock_asyncio, \
         patch('concurrent.futures.ThreadPoolExecutor') as MockExecutor:
        
        mock_instance = MagicMock()
        MockService.return_value = mock_instance
        
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_asyncio.get_event_loop.return_value = mock_loop
        
        adapter = CouncilAgentAdapter()
        
        mock_executor_instance = MagicMock()
        MockExecutor.return_value.__enter__.return_value = mock_executor_instance
        
        mock_future = MagicMock()
        mock_future.result.return_value = {"result": "threaded"}
        mock_executor_instance.submit.return_value = mock_future
        
        result = adapter.run({})
        
        assert result["result"] == "threaded"
        # Check that it submitted asyncio.run
        args = mock_executor_instance.submit.call_args
        assert args[0][0] == mock_asyncio.run
