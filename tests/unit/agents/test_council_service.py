import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.council_service import CouncilService

@pytest.fixture
def mock_deps():
    """Mock dependencies for CouncilService PAD Phase 2 refactor."""
    with patch('src.services.council_service.AlchemyVectorRepository') as mock_vector, \
         patch('src.services.council_service.LaneManager') as mock_lane_cls, \
         patch('src.services.council_service.CouncilTierRouter') as mock_router, \
         patch('src.services.council_service.SettingsAwareModelRouter') as mock_model_router, \
         patch('src.services.council_service.AlchemySettingsRepository') as mock_settings_repo, \
         patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_chain, \
         patch('src.services.council_service.OpenRouterGateway') as mock_gateway_cls:
        
        # Setup LaneManager instance mock
        mock_lane_instance = MagicMock()
        mock_lane_instance.run_batch = AsyncMock()
        mock_lane_instance.run_batch.return_value = [
            {"ticker": "AAPL", "momentum": "UP", "fundamental": "GOOD", "quantity": 10},
            {"ticker": "GOOGL", "momentum": "DOWN", "fundamental": "OK", "quantity": 5}
        ]
        mock_lane_cls.return_value = mock_lane_instance
        
        # Setup CouncilTierRouter mock
        mock_router_instance = MagicMock()
        mock_router_instance.select_tier = MagicMock(return_value="smart")
        mock_router.return_value = mock_router_instance
        
        # Setup SettingsAwareModelRouter mock
        mock_model_router_instance = MagicMock()
        mock_model_router_instance.get_model = MagicMock(return_value="openrouter/meta-llama/llama-2-7b")
        mock_model_router.return_value = mock_model_router_instance
        
        # Setup OpenRouterGateway mock
        mock_gateway_instance = MagicMock()
        mock_gateway_instance.chat = AsyncMock(return_value='{"analysis": "test response"}')
        mock_gateway_cls.return_value = mock_gateway_instance

        # Setup build_config_chain mock
        mock_chain.return_value = MagicMock() # Return a dummy chain object
        
        yield {
            "vector": mock_vector,
            "lane": mock_lane_instance,
            "router": mock_router_instance,
            "model_router": mock_model_router_instance,
            "settings_repo": mock_settings_repo,
            "gateway": mock_gateway_instance,
            "chain": mock_chain
        }

def test_start_session_map_reduce(mock_deps):
    """Test CouncilService with Map-Reduce flow (PAD Phase 2)."""
    async def run_test():
        service = CouncilService(user_id="test_user")
        
        # Mock _call_agent_llm to return predictable responses
        with patch.object(service, '_call_agent_llm', new_callable=AsyncMock) as mock_agent_call:
            mock_agent_call.return_value = "Agent analysis response"
            
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
            
            # Verify Result Structure
            assert result["type"] == "map-reduce"
            assert "session_id" in result
            assert "consensus" in result
            assert "transcript" in result
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_start_session_standard(mock_deps):
    """Test CouncilService with standard single-topic flow (PAD Phase 2)."""
    async def run_test():
        service = CouncilService(user_id="test_user")
        
        # Mock _call_agent_llm for all agent calls
        with patch.object(service, '_call_agent_llm', new_callable=AsyncMock) as mock_agent_call:
            mock_agent_call.return_value = "Agent stance response"
            
            context = {"topic": "TSLA Analysis", "market_data": {}}
            
            result = await service.start_session(
                topic="TSLA Analysis",
                context_data=context,
                user_id="test_user",
                scope="single"
            )
            
            # Verify result structure
            assert "session_id" in result
            assert "consensus" in result
            assert "transcript" in result
            
            # Verify that _call_agent_llm was called (5 agents + 1 CIO)
            assert mock_agent_call.call_count >= 6
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_call_agent_llm_success(mock_deps):
    """Test _call_agent_llm helper method with successful response."""
    async def run_test():
        service = CouncilService(user_id="test_user")
        
        # Mock ResilientLLMPipeline.execute to return valid string
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ('{"analysis": "Momentum is bullish"}', None)
            
            result = await service._call_agent_llm(
                "Momentum",
                {"ticker": "AAPL", "price": 150},
                tier="fast"
            )
            
            assert isinstance(result, str)
            assert "analysis" in result
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_call_agent_llm_error_handling(mock_deps):
    """Test _call_agent_llm error handling with non-string response."""
    async def run_test():
        service = CouncilService(user_id="test_user")
        
        # Mock ResilientLLMPipeline.execute to return HTML error (non-string like dict)
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ({"error": "HTML error"}, None)
            
            with pytest.raises(ValueError, match="Unexpected response type"):
                await service._call_agent_llm(
                    "Momentum",
                    {"ticker": "AAPL"},
                    tier="fast"
                )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_call_agent_llm_model_routing(mock_deps):
    """Test _call_agent_llm correctly routes model by tier."""
    async def run_test():
        service = CouncilService(user_id="test_user")
        
        # Configure mock model router and pipeline
        mock_deps['model_router'].get_model = MagicMock(return_value="gpt-3.5-turbo")
        
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ('{"result": "ok"}', None)
            
            await service._call_agent_llm(
                "Fundamental",
                {"ticker": "AAPL"},
                tier="smart"
            )
            
            # Verify model router was called with correct tier
            # (Note: model_router is now used inside build_config_chain, but we mocked build_config_chain in mock_deps)
            # Actually, since we mocked build_config_chain, model_router won't be called unless we unmock it.
            # In the current PAD Phase 2, CouncilService calls build_config_chain(self.user_id, tier).
            assert mock_deps['chain'].called
            args, kwargs = mock_deps['chain'].call_args
            assert args[0] == "test_user"
            assert args[1] == "smart"
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()
