import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.council_service import CouncilService

@pytest.fixture
def council_service():
    with patch('src.services.council_service.AlchemyVectorRepository'), \
         patch('src.services.council_service.LaneManager'), \
         patch('src.services.council_service.AlchemySettingsRepository'), \
         patch('src.data.database.get_db_engine'):
        yield CouncilService(user_id="test_user")

@pytest.mark.asyncio
async def test_call_agent_llm_success(council_service):
    agent_name = "Momentum"
    context = {"ticker": "AAPL"}
    mock_response = "Bullish momentum detected."
    
    with patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_build_chain:
        mock_build_chain.return_value = ["mock_config"]
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = (mock_response, None)
            with patch('src.utils.prompt_utils.load_agent_prompt', return_value="System prompt"):
                
                result = await council_service._call_agent_llm(agent_name, context)
                
                assert result == mock_response
                mock_execute.assert_called_once()

@pytest.mark.asyncio
async def test_start_session_single(council_service):
    topic = "Analysis of TSLA"
    context_data = {"market_data": {}}
    user_id = "test_user"
    
    with patch.object(council_service, '_run_debate_logic', new_callable=AsyncMock) as mock_debate:
        mock_debate.return_value = {"session_id": "123", "consensus": "Buy", "transcript": []}
        
        result = await council_service.start_session(topic, context_data, user_id, scope="single")
        
        assert result["session_id"] == "123"
        mock_debate.assert_called_once()

@pytest.mark.asyncio
async def test_run_map_reduce_portfolio(council_service):
    session_id = "123"
    topic = "Portfolio Analysis"
    context_data = {
        "portfolio": [{"symbol": "AAPL", "quantity": 10}, {"symbol": "MSFT", "quantity": 5}],
        "market_data": {}
    }
    user_id = "test_user"
    
    with patch.object(council_service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [
            "Mom AAPL", "Fun AAPL", # AAPL
            "Mom MSFT", "Fun MSFT", # MSFT
            "Final CIO Consensus"   # CIO
        ]

        async def fake_run_batch(tasks, batch_size=5):
            return [await t() for t in tasks]

        council_service.lane_manager.run_batch = fake_run_batch

        with patch.object(council_service, '_archive_minutes'):
            result = await council_service._run_map_reduce_portfolio(session_id, topic, context_data, user_id)
            
            assert "Final CIO Consensus" in result["consensus"]
            assert "AAPL" in result["transcript"]
            assert "MSFT" in result["transcript"]
            assert mock_call.call_count == 5

@pytest.mark.asyncio
async def test_run_debate_logic_with_past_wisdom(council_service):
    session_id = "123"
    topic = "Analysis of NVDA"
    context_data = {"market_data": {}}
    user_id = "test_user"
    
    with patch.object(council_service.vector_repo, 'search_similar_minutes') as mock_search:
        mock_search.return_value = [{"topic": "NVDA", "consensus": "Keep buying"}]
        
        with patch.object(council_service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Agent opinion"
            
            with patch('src.services.user_focus_service.UserFocusService.get_user_focus', return_value="Growth"):
                with patch.object(council_service, '_archive_minutes'):
                    result = await council_service._run_debate_logic(session_id, topic, context_data, user_id)
                    
                    assert result["session_id"] == "123"
                    assert "Agent opinion" in result["consensus"]
                    # 5 agents + 1 CIO = 6 calls
                    assert mock_call.call_count == 6
