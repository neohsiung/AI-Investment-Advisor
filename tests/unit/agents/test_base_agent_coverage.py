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

        # Mocking prompt loading to avoid file system error.
        # The conftest autouse fixture (mock_build_config_chain) patches build_config_chain
        # globally, so the agent can initialize with user_id provided.
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="System Prompt {{ name }}")):

            agent = ConcreteAgent(
                name="TestAgent",
                prompt_path="dummy_prompt.txt",
                user_id="test_user",   # Required: _load_config raises without user_id
                settings_repo=mock_settings,
                state_repo=mock_state
            )
        return agent

    def test_init_defaults(self, agent):
        assert agent.name == "TestAgent"
        # Default tier is "smart"
        assert 'model' in agent.config

    def test_load_config_priority(self):
        """
        _load_config() reads from llm_tier_bindings (via build_config_chain).
        The conftest autouse fixture patches build_config_chain to return a mock
        candidate with model_code='mock-model'. Verify the config is populated
        from the candidate returned by get_config_chain().
        """
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="Prompt")):

            mock_settings_repo = MagicMock()
            mock_settings_repo.get_all.return_value = [("AI_MODEL_SMART", "gemini-1.5-ultra")]

            # The conftest autouse fixture ensures build_config_chain returns a mock candidate.
            # We do NOT patch get_config_chain to [] here — that would raise ValueError.
            agent = ConcreteAgent(name="A", prompt_path="p", user_id="user1", settings_repo=mock_settings_repo)

        # Config is built from the mock candidate returned by the conftest fixture.
        assert agent.config['model'] == "mock-model"

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
        from unittest.mock import AsyncMock
        agent.call_llm = AsyncMock(side_effect=[
            'SEARCH: "AAPL"',
            'Analysis of AAPL'
        ])

        # Mock search service import inside method
        from unittest.mock import AsyncMock
        with patch('src.services.search_service.InternetSearchService') as mock_search_cls:
            mock_svc = mock_search_cls.return_value
            mock_svc.search_financial_context = AsyncMock(return_value=[{'title': 'AAPL', 'snippet': '150', 'link': 'url'}])

            res = await agent.run_tool_loop(context)

            mock_svc.search_financial_context.assert_called_once_with("AAPL", max_results=3)

    @pytest.mark.asyncio
    async def test_call_real_llm(self, agent):
        """Test _call_real_llm delegates through gateway (via call_llm)."""
        agent.config['api_key'] = 'secret'
        agent.config['provider'] = 'OpenRouter'
        agent.config['model'] = 'model-x'

        # Patch the gateway directly since _call_real_llm now bridges to call_llm -> gateway
        from unittest.mock import AsyncMock
        mock_gw = MagicMock()
        mock_gw.chat = AsyncMock(return_value="Real Logic Output")
        agent._llm_gateway = mock_gw

        res = await agent._call_real_llm("prompt", "sys")
        assert res == "Real Logic Output"

        # Test Google Gemini path (same gateway, different config)
        agent.config['provider'] = 'Google Gemini'
        mock_gw.chat = AsyncMock(return_value="Gemini Output")

        res = await agent._call_real_llm("prompt", "sys")
        assert res == "Gemini Output"
