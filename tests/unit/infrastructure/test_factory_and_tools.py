import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
from src.agents.factory import AgentFactory
from src.agents.base_agent import BaseAgent

class MockAgent(BaseAgent):
    async def run(self, context):
        return await self.run_tool_loop(context)

@pytest.mark.asyncio
async def test_factory_tiers():
    # Verify Tier Enforcement
    # v11.5: Patching sub-agents and repositories to prevent side-effects during swarm init
    with patch('src.agents.factory.AgentFactory._configure_dspy'), \
         patch('src.agents.factory.create_market_server') as mock_market_server, \
         patch('src.agents.swarm.momentum_swarm.MomentumScanner'), \
         patch('src.agents.swarm.fundamental_swarm.FundamentalSubAgent'), \
         patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}), \
         patch('src.agents.base_agent.AlchemySettingsRepository'), \
         patch('src.agents.base_agent.AlchemyAgentStateRepository'), \
         patch('src.agents.base_agent.AlchemyFeedbackRepository'), \
         patch('src.agents.base_agent.HybridMemory'), \
         patch('src.services.cognitive_memory_manager.CognitiveMemoryManager'), \
         patch('src.agents.base_agent.SkillLoader'), \
         patch('src.repositories.prompt_repository.AlchemyPromptRepository'):
        
        # Setup mock market server
        mock_market_server.return_value.list_tools.return_value = []
        
        mom_agent = AgentFactory.create_momentum_agent(use_cache=False, user_id="test-user")
        assert mom_agent.tier == "fast"
        
        fund_agent = AgentFactory.create_fundamental_agent(use_cache=False, user_id="test-user")
        assert fund_agent.tier == "smart"
        
        cio_agent = AgentFactory.create_cio_agent(use_cache=False, user_id="test-user")
        assert cio_agent.tier == "smart"

@pytest.mark.asyncio
async def test_run_tool_loop():
    # We need to patch the InternetSearchService CLASS that BaseAgent imports.
    with patch('src.services.search_service.InternetSearchService') as MockSearchServiceClass:
        mock_instance = MockSearchServiceClass.return_value
        mock_instance.search_financial_context = AsyncMock(return_value=[{'snippet': 'Search Result', 'title': 'T', 'link': 'L'}])
        
        with patch('src.agents.base_agent.BaseAgent.call_llm') as MockCallLLM:
            MockCallLLM.side_effect = [
                'SEARCH: "query"',       # Turn 1: Request Search
                'Final Answer'           # Turn 2: Final Response
            ]
            
            # Module-level patching for all components used in BaseAgent.__init__
            with patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}), \
                 patch('src.repositories.settings_repository.AlchemySettingsRepository'), \
                 patch('src.repositories.agent_state_repository.AlchemyAgentStateRepository'), \
                 patch('src.repositories.feedback_repository.AlchemyFeedbackRepository'), \
                 patch('src.services.cognitive_memory_manager.CognitiveMemoryManager'), \
                 patch('src.agents.base_agent.HybridMemory'), \
                 patch('src.agents.base_agent.SkillLoader'), \
                 patch('src.repositories.prompt_repository.AlchemyPromptRepository'):
                
                agent = MockAgent(name="Test", prompt_path="prompts/cio_weekly.txt", use_cache=False, user_id="test-user")
                response = await agent.run({"data": "test"})
                
                assert "Final Answer" in response
                assert MockCallLLM.call_count == 2
                
                # Verify Search called with max_results=3
                mock_instance.search_financial_context.assert_called_with("query", max_results=3)
