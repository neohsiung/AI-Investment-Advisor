import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.council_service import CouncilService

@pytest.fixture
def mock_deps():
    with patch('src.services.council_service.AgentFactory') as mock_factory, \
         patch('src.services.council_service.AlchemyVectorRepository') as mock_vector, \
         patch('src.services.council_service.LaneManager') as mock_lane_cls, \
         patch('src.services.council_service.CouncilTierRouter') as mock_router:
        
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
        service = CouncilService(user_id="test_user")
        
        # Mock output of Agents
        mock_deps['factory'].create_cio_agent.return_value.run = AsyncMock(return_value="Final Consensus Report")
        
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
            user_id="test_user",
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
        service = CouncilService(user_id="test_user")
        
        # Mock _run_debate_logic to avoid deep agent logic
        with patch.object(service, '_run_debate_logic', new_callable=AsyncMock) as mock_debate:
            mock_debate.return_value = {"session_id": "123", "consensus": "Standard Decision", "transcript": []}
            
            context = {"market_data": {}}
            result = await service.start_session(
                topic="Single Stock",
                context_data=context,
                user_id="test_user",
                scope="single"
            )
            
            assert result["consensus"] == "Standard Decision"
            mock_debate.assert_called_once()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

@pytest.mark.asyncio
async def test_run_debate_logic_directly(mock_deps):
    """Test the asynchronous logic underlying standard session."""
    service = CouncilService(user_id="test_user")
    
    # Mock Agents
    mock_agent = MagicMock()
    # Agent.run is async
    mock_agent.run = AsyncMock(return_value="Analysis Result")
    mock_agent.name = "TestAgent"
    
    # Mock Factory to return agents
    mock_deps['factory'].create_momentum_agent.return_value = mock_agent
    mock_deps['factory'].create_fundamental_agent.return_value = mock_agent
    mock_deps['factory'].create_risk_agent.return_value = mock_agent
    mock_deps['factory'].create_sentiment_agent.return_value = mock_agent
    mock_deps['factory'].create_macro_agent.return_value = mock_agent
    
    # CIO run is also async
    mock_cio = MagicMock()
    mock_cio.run = AsyncMock(return_value="Consensus")
    mock_deps['factory'].create_cio_agent.return_value = mock_cio

    # Mock Router
    mock_deps['router'].return_value.select_tier.return_value = "fast"
    
    context = {"market_data": {}}
    result = await service._run_debate_logic("sess_id", "Topic", context, user_id="test_user")
    
    assert result["consensus"] == "Consensus"
    assert len(result["transcript"]) == 5 # 5 agents
    assert "[TestAgent]: Analysis Result" in result["transcript"][0]
    
    # Verify Archive
    mock_deps['vector'].return_value.add_council_minute.assert_called()
