
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.factory import AgentFactory
from src.agents.base_agent import BaseAgent

class MockAgent(BaseAgent):
    async def run(self, context):
        return await self.run_tool_loop(context)

class TestAgentFactoryAndTools:
    
    def test_factory_tiers(self):
        # Verify Tier Enforcement
        # We mock _configure_dspy to avoid API config issues
        with patch('src.agents.factory.AgentFactory._configure_dspy'):
            # Also patch BaseAgent load config to avoid DB
            with patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}):
                mom_agent = AgentFactory.create_momentum_agent(use_cache=False)
                assert mom_agent.tier == "fast"
                
                fund_agent = AgentFactory.create_fundamental_agent(use_cache=False)
                assert fund_agent.tier == "smart"
                
                cio_agent = AgentFactory.create_cio_agent(use_cache=False)
                assert cio_agent.tier == "smart"

    @pytest.mark.asyncio
    @patch('src.agents.base_agent.BaseAgent.call_llm', new_callable=AsyncMock)
    async def test_run_tool_loop(self, MockCallLLM):
        # We need to patch the InternetSearchService CLASS that BaseAgent imports.
        # Since it is imported inside the method 'run_tool_loop' as:
        # from src.services.search_service import InternetSearchService
        # We patch 'src.services.search_service.InternetSearchService'
        
        with patch('src.services.search_service.InternetSearchService') as MockSearchServiceClass:
            mock_instance = MockSearchServiceClass.return_value
            mock_instance.search_financial_context.return_value = [{'snippet': 'Search Result'}]
            
            # Mock LLM conversation
            MockCallLLM.side_effect = [
                'SEARCH: "query"',       # Turn 1: Request Search
                'Final Answer'           # Turn 2: Final Response
            ]
            
            # Patch _load_prompt and _load_config to avoid external dependencies
            with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Test Prompt"):
                with patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}):
                    agent = MockAgent(name="Test", prompt_path="prompts/cio_weekly.txt", use_cache=False)
                    response = await agent.run({"data": "test"})
                    
                    assert "Final Answer" in response
                    assert MockCallLLM.call_count == 2
                    
                    # Verify Search called (agent_loop passes only query, no max_results kwarg)
                    mock_instance.search_financial_context.assert_called_with("query")

if __name__ == '__main__':
    pytest.main([__file__])
