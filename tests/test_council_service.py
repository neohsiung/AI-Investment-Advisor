import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.council_service import CouncilService

@pytest.fixture
def mock_deps():
    with patch('src.services.council_service.AgentFactory') as mock_factory, \
         patch('src.services.council_service.AlchemyVectorRepository') as mock_vector, \
         patch('src.services.council_service.LaneManager') as mock_lane_cls, \
         patch('src.services.council_service.DynamicModelRouter') as mock_router:
        
        # Setup LaneManager instance mock
        mock_lane_instance = MagicMock()
        # run_batch should be async
        mock_lane_instance.run_batch = AsyncMock()
        mock_lane_instance.run_batch.return_value = [
            {"ticker": "AAPL", "momentum": "UP", "fundamental": "GOOD", "quantity": 10},
            {"ticker": "GOOGL", "momentum": "DOWN", "fundamental": "OK", "quantity": 5}
        ]
        mock_lane_cls.return_value = mock_lane_instance
        
        yield {
            "factory": mock_factory,
            "vector": mock_vector,
            "lane": mock_lane_instance,
            "router": mock_router
        }

def test_start_session_map_reduce(mock_deps):
    async def run_test():
        service = CouncilService()
        
        # Mock output of Agents
        mock_deps['factory'].create_cio_agent.return_value.run.return_value = "Final Consensus Report"
        
        context = {
            "portfolio": [
                {"symbol": "AAPL", "quantity": 10},
                {"symbol": "GOOGL", "quantity": 5}
            ],
            "market_data": {}
        }
        
        # We need to ensure that when service calls asyncio.get_running_loop(), it gets our loop
        # But run_until_complete sets the running loop? Yes, usually.
        
        result = await service.start_session(
            topic="Portfolio Review",
            context_data=context,
            scope="portfolio"
        )
        
        # Verify Map Phase (LaneManager called)
        assert mock_deps['lane'].run_batch.called
        
        # Verify Reduce Phase (Factory called for CIO)
        mock_deps['factory'].create_cio_agent.assert_called()
        
        # Verify Result Structure
        assert result["type"] == "map-reduce"
        assert "Final Consensus Report" in result["consensus"]
        assert "AAPL" in result["transcript"]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_start_session_standard(mock_deps):
    async def run_test():
        service = CouncilService()
        
        # Mock run_in_executor to execute the sync function immediately
        # We need to patch the loop in CouncilService
        with patch('src.services.council_service.asyncio.get_running_loop') as mock_loop_getter:
            mock_loop = MagicMock()
            
            # Mock Future for run_in_executor
            f = asyncio.Future()
            f.set_result({"session_id": "123", "consensus": "Standard Decision", "transcript": []})
            mock_loop.run_in_executor.return_value = f
            
            mock_loop_getter.return_value = mock_loop
            
            context = {"market_data": {}}
            result = await service.start_session(
                topic="Single Stock",
                context_data=context,
                scope="single"
            )
            
            assert result["consensus"] == "Standard Decision"
            
            # Verify run_in_executor called with correct target
            # args[0] is None (executor), args[1] is func
            # args = mock_loop.run_in_executor.call_args
            # assert args[0][1] == service._run_sync_logic
            # (call_args might be simpler)
            mock_loop.run_in_executor.assert_called()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_run_sync_logic_directly(mock_deps):
    """Test the synchronous logic underlying standard session."""
    service = CouncilService()
    
    # Mock Agents
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Analysis Result"
    mock_agent.name = "TestAgent"
    
    # Mock Factory to return agents
    mock_deps['factory'].create_momentum_agent.return_value = mock_agent
    mock_deps['factory'].create_fundamental_agent.return_value = mock_agent
    mock_deps['factory'].create_risk_agent.return_value = mock_agent
    mock_deps['factory'].create_sentiment_agent.return_value = mock_agent
    mock_deps['factory'].create_macro_agent.return_value = mock_agent
    mock_deps['factory'].create_cio_agent.return_value.run.return_value = "Consensus"

    # Mock Router
    mock_deps['router'].return_value.select_tier.return_value = "fast"
    
    context = {"market_data": {}}
    result = service._run_sync_logic("sess_id", "Topic", context)
    
    assert result["consensus"] == "Consensus"
    assert len(result["transcript"]) == 5 # 5 agents
    assert "[TestAgent]: Analysis Result" in result["transcript"][0]
    
    # Verify Archive
    mock_deps['vector'].return_value.add_council_minute.assert_called()
