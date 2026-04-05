import pytest
from unittest.mock import MagicMock, patch, ANY, mock_open, AsyncMock
from src.agents.base_agent import BaseAgent

class ConcreteAgent(BaseAgent):
    async def run(self, context):
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

    @pytest.mark.asyncio
    async def test_call_llm_mock(self, agent):
        # Override the gateway to use MockLLMGateway for the test
        from src.infrastructure.llm.llm_gateway import MockLLMGateway
        agent._llm_gateway = MockLLMGateway()
        
        res = await agent.call_llm([{"role": "user", "content": "Hi"}])
        assert "Simulation Mode" in res or "TestAgent" in res or "[Mock Output]" in res

    @pytest.mark.asyncio
    async def test_run_tool_loop_search(self, agent):
        # Test tool loop calling search
        context = {}
        
        # Mock call_llm to return SEARCH then answer
        # Must be AsyncMock because it's awaited
        agent.call_llm = AsyncMock(side_effect=[
            'SEARCH: "AAPL"',
            'Analysis of AAPL'
        ])
        
        # Mock search service import inside method
        with patch('src.services.search_service.InternetSearchService') as mock_search_cls:
            mock_svc = MagicMock()
            mock_search_cls.return_value = mock_svc
            mock_svc.search_financial_context.return_value = [{'title': 'AAPL', 'snippet': '150', 'link': 'url'}]
            
            # Since AgentLoop now uses to_thread for SEARCH, search_svc must be sync-capable
            agent._search_service = mock_svc
            
            res = await agent.run_tool_loop(context)
            
            mock_svc.search_financial_context.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_call_real_llm(self, agent):
        """Test _call_real_llm delegates through gateway (via call_llm)."""
        agent.config['api_key'] = 'secret'
        agent.config['provider'] = 'OpenRouter'
        agent.config['model'] = 'model-x'
        
        # Patch the gateway directly since _call_real_llm now bridges to call_llm -> gateway
        mock_gw = AsyncMock()
        mock_gw.chat.return_value = "Real Logic Output"
        agent._llm_gateway = mock_gw
        
        res = await agent._call_real_llm("prompt", "sys")
        assert res == "Real Logic Output"
        
        # Test Google Gemini path (same gateway, different config)
        agent.config['provider'] = 'Google Gemini'
        mock_gw.chat.return_value = "Gemini Output"
        
        res = await agent._call_real_llm("prompt", "sys")
        assert res == "Gemini Output"
