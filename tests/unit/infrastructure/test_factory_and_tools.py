
import unittest
from unittest.mock import MagicMock, patch
import sys
from src.agents.factory import AgentFactory
from src.agents.base_agent import BaseAgent

class MockAgent(BaseAgent):
    def run(self, context):
        return self.run_tool_loop(context)

class TestAgentFactoryAndTools(unittest.TestCase):
    
    def test_factory_tiers(self):
        # Verify Tier Enforcement
        # We mock _configure_dspy to avoid API config issues
        with patch('src.agents.factory.AgentFactory._configure_dspy'):
            # Also patch BaseAgent load config to avoid DB
            with patch('src.agents.base_agent.BaseAgent._load_config', return_value={"model": "test", "provider": "test"}):
                mom_agent = AgentFactory.create_momentum_agent(use_cache=False)
                self.assertEqual(mom_agent.tier, "fast")
                
                fund_agent = AgentFactory.create_fundamental_agent(use_cache=False)
                self.assertEqual(fund_agent.tier, "smart")
                
                cio_agent = AgentFactory.create_cio_agent(use_cache=False)
                self.assertEqual(cio_agent.tier, "smart")

    @patch('src.agents.base_agent.BaseAgent.call_llm')
    def test_run_tool_loop(self, MockCallLLM):
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
            
            agent = MockAgent(name="Test", prompt_path="prompts/cio_weekly.txt", use_cache=False)
            response = agent.run({"data": "test"})
            
            self.assertIn("Final Answer", response)
            self.assertEqual(MockCallLLM.call_count, 2)
            
            # Verify Search called
            mock_instance.search_financial_context.assert_called_with("query", max_results=3)

if __name__ == '__main__':
    unittest.main()
