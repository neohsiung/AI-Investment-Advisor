import pytest
from unittest.mock import MagicMock, patch, ANY, mock_open
from src.agents.base_agent import BaseAgent

class ConcreteAgent(BaseAgent):
    def run(self, context):
        return "Run Output"

class TestBaseAgentCoverage:
    @pytest.fixture
    def agent(self):
        mock_settings = MagicMock()
        mock_settings.get_global.return_value = []
        mock_settings.get_all.return_value = []
        
        mock_state = MagicMock()
        
        # Mocking prompt loading to avoid file system error
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="System Prompt {{ name }}")):
            
            agent = ConcreteAgent(
                name="TestAgent", 
                prompt_path="dummy_prompt.txt",
                settings_repo=mock_settings,
                state_repo=mock_state
            )
        return agent

    def test_init_defaults(self, agent):
        assert agent.name == "TestAgent"
        # Default tier is "smart"
        assert 'model' in agent.config

    def test_load_config_priority(self):
        # Mock DB, Env and File System for new instance
        # Remove invalid patch of SettingsService
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="Prompt")):
            
            # Test Env Var override (simulated by _load_config logic if DB empty)
            # Actually BaseAgent loads from os.getenv.
            # We want to test DB override.
            
            mock_settings_repo = MagicMock()
            # Mock the return value to be a list of tuples since BaseAgent handles that
            mock_settings_repo.get_all.return_value = [("AI_MODEL_SMART", "gemini-1.5-ultra")]
            
            agent = ConcreteAgent(name="A", prompt_path="p", user_id="user1", settings_repo=mock_settings_repo)
            assert agent.config['model'] == "gemini-1.5-ultra"

    def test_render_system_prompt(self, agent):
        agent.system_prompt = "Hello {{ name }}"
        res = agent.render_system_prompt({"name": "World"})
        assert res == "Hello World"

    def test_check_freshness(self, agent):
        agent.state_repo = MagicMock()
        
        # New hash
        agent._compute_hash = MagicMock(return_value="hash1")
        agent.state_repo.get_state.return_value = None
        
        is_fresh, h, prev = agent.check_freshness({})
        assert is_fresh
        assert h == "hash1"

        # Same hash
        agent.state_repo.get_state.return_value = ("hash1", "old_out")
        is_fresh, h, prev = agent.check_freshness({})
        assert not is_fresh
        assert prev == "old_out"

    def test_update_state(self, agent):
        agent.state_repo = MagicMock()
        agent.update_state("hash1", "output")
        agent.state_repo.save_state.assert_called_with("TestAgent", "TestAgent", "hash1", "output")

    def test_call_llm_mock(self, agent):
        # Test _call_llm logic
        # Mock _call_real_llm to avoid hitting API if keys present
        # Mock config to have no key -> Mock
        agent.config['api_key'] = ''
        res = agent.call_llm([{"role": "user", "content": "Hi"}])
        assert "Simulation Mode" in res or "TestAgent" in res

    def test_run_tool_loop_search(self, agent):
        # Test tool loop calling search
        context = {}
        
        # Mock call_llm to return SEARCH then answer
        agent.call_llm = MagicMock(side_effect=[
            'SEARCH: "AAPL"',
            'Analysis of AAPL'
        ])
        
        # Mock search service import inside method
        with patch('src.services.search_service.InternetSearchService') as mock_search_cls:
            mock_svc = mock_search_cls.return_value
            mock_svc.search_financial_context.return_value = [{'title': 'AAPL', 'snippet': '150', 'link': 'url'}]
            
            res = agent.run_tool_loop(context)
            
            mock_svc.search_financial_context.assert_called_with("AAPL", max_results=3)

    def test_call_real_llm(self, agent):
        # Test _call_real_llm by mocking requests
        # We need to set api_key in config to trigger real call logic if we weren't mocking call_llm wrapper.
        # But here we call _call_real_llm DIRECTLY or via call_llm with key.
        agent.config['api_key'] = 'secret'
        agent.config['provider'] = 'OpenRouter'
        agent.config['model'] = 'model-x'
        
        with patch('src.agents.base_agent.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                'choices': [{'message': {'content': 'Real Logic Output'}}]
            }
            mock_post.return_value = mock_resp
            
            # We call the method directly to ensure we hit it even if _mock_llm_call has bypass logic
            # Actually BaseAgent.call_llm calls _mock_llm_call which calls _call_real_llm if api_key exists.
            
            # Ensure _call_real_llm is reachable
            res = agent._call_real_llm("prompt", "sys")
            assert res == "Real Logic Output"
            
            # Test Google Gemini path
            agent.config['provider'] = 'Google Gemini'
            mock_resp.json.return_value = {
                'candidates': [{'content': {'parts': [{'text': 'Gemini Output'}]}}]
            }
            res = agent._call_real_llm("prompt", "sys")
            assert res == "Gemini Output"
