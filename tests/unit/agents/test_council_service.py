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

@pytest.mark.asyncio
async def test_start_session_map_reduce(mock_deps):
    service = CouncilService(user_id="test_user")
    
    # Mock output of Agents
    mock_agent = AsyncMock()
    mock_agent.run.return_value = "Final Consensus Report"
    mock_deps['factory'].create_cio_agent.return_value = mock_agent
    
    context = {
        "portfolio": [
            {"symbol": "AAPL", "quantity": 10},
            {"symbol": "GOOGL", "quantity": 5}
        ],
        "market_data": {}
    }
    
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

@pytest.mark.asyncio
async def test_start_session_standard(mock_deps):
    service = CouncilService(user_id="test_user")
    
    # Mock agents and CIO
    mock_agent = AsyncMock()
    mock_agent.run.return_value = "Standard Decision"
    mock_deps['factory'].create_momentum_agent.return_value = mock_agent
    mock_deps['factory'].create_fundamental_agent.return_value = mock_agent
    mock_deps['factory'].create_risk_agent.return_value = mock_agent
    mock_deps['factory'].create_sentiment_agent.return_value = mock_agent
    mock_deps['factory'].create_macro_agent.return_value = mock_agent
    mock_deps['factory'].create_cio_agent.return_value = mock_agent
    
    # Mock Vector Repo
    mock_deps['vector'].return_value.search_similar_minutes.return_value = []
    
    # Mock Router
    mock_deps['router'].return_value.select_tier.return_value = "fast"
    
    context = {"market_data": {}}
    result = await service.start_session(
        topic="Single Stock",
        context_data=context,
        user_id="test_user",
        scope="single"
    )
    
    assert result["consensus"] == "Standard Decision"
    assert "Standard Decision" in result["consensus"]

@pytest.mark.asyncio
async def test_run_async_logic_directly(mock_deps):
    """Test the asynchronous logic underlying standard session."""
    service = CouncilService(user_id="test_user")
    
    # Mock Agents
    mock_agent = AsyncMock()
    mock_agent.run.return_value = "Analysis Result"
    mock_agent.name = "TestAgent"
    
    # Mock Factory to return agents
    mock_deps['factory'].create_momentum_agent.return_value = mock_agent
    mock_deps['factory'].create_fundamental_agent.return_value = mock_agent
    mock_deps['factory'].create_risk_agent.return_value = mock_agent
    mock_deps['factory'].create_sentiment_agent.return_value = mock_agent
    mock_deps['factory'].create_macro_agent.return_value = mock_agent
    
    mock_cio = AsyncMock()
    mock_cio.run.return_value = "Consensus"
    mock_deps['factory'].create_cio_agent.return_value = mock_cio

    # Mock Router
    mock_deps['router'].return_value.select_tier.return_value = "fast"
    
    # Mock Vector Repo
    mock_deps['vector'].return_value.search_similar_minutes.return_value = []
    
    context = {"market_data": {}}
    result = await service._run_async_logic("sess_id", "Topic", context, user_id="test_user")
    
    assert result["consensus"] == "Consensus"
    assert len(result["transcript"]) == 5 # 5 agents
    assert "[TestAgent]: Analysis Result" in result["transcript"][0]
    
    # Verify Archive
    mock_deps['vector'].return_value.add_council_minute.assert_called()
