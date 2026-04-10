
import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import json
from src.agents.base_agent import BaseAgent

class ConcreteAgent(BaseAgent):
    def run(self, context):
        return "Concreted"

class TestBaseAgentMoreCoverage:
    
    @pytest.fixture
    def mock_settings_repo(self):
        return Mock()

    @pytest.fixture
    def mock_state_repo(self):
        return Mock()

    @pytest.fixture
    def agent(self, mock_settings_repo, mock_state_repo):
        # Patch prompt loading to avoid file IO
        with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
             # Patch _load_config to avoid complex lookup during init, we test it separately
             with patch.object(BaseAgent, '_load_config', return_value={"provider": "Mock"}):
                 agent = ConcreteAgent("TestAgent", "path", 
                                       settings_repo=mock_settings_repo, 
                                       state_repo=mock_state_repo)
                 return agent

    def test_load_config_db_priority(self, mock_settings_repo, mock_state_repo):
        # Setup DB mocks
        mock_settings_repo.get_all.return_value = [("AI_PROVIDER", "DB_GEMINI")]
        
        with patch.object(BaseAgent, '_load_prompt', return_value=""):
             # We want to test the REAL _load_config
             agent = ConcreteAgent("TestAgent", "path", user_id="test_user", settings_repo=mock_settings_repo, state_repo=mock_state_repo)
             # _load_config is called in __init__
             
             assert agent.config['provider'] == "DB_GEMINI"

    def test_load_config_tier_smart(self, mock_settings_repo, mock_state_repo):
        mock_settings_repo.get_all.return_value = [("AI_MODEL_SMART", "gemini-ultra")]
        
        with patch.object(BaseAgent, '_load_prompt', return_value=""):
             agent = ConcreteAgent("TestAgent", "path", user_id="test_user", tier="smart", settings_repo=mock_settings_repo, state_repo=mock_state_repo)
             assert agent.config['model'] == "gemini-ultra"

    def test_load_config_tier_fast(self, mock_settings_repo, mock_state_repo):
        mock_settings_repo.get_all.return_value = [("AI_MODEL_FAST", "gemini-flash")]
        
        with patch.object(BaseAgent, '_load_prompt', return_value=""):
             agent = ConcreteAgent("TestAgent", "path", user_id="test_user", tier="fast", settings_repo=mock_settings_repo, state_repo=mock_state_repo)
             assert agent.config['model'] == "gemini-flash"

    def test_check_freshness_hash_match(self, agent):
        context = {"key": "val"}
        state_key = "sk"
        
        # Mock compute hash
        agent._compute_hash = Mock(return_value="hash123")
        
        # Mock state repo get_state -> (hash, output)
        agent.state_repo.get_state.return_value = ("hash123", "Result")
        
        run, h, out = agent.check_freshness(context, state_key)
        assert run is False
        assert out == "Result"

    def test_check_freshness_hash_mismatch(self, agent):
        context = {"key": "val"}
        agent._compute_hash = Mock(return_value="hashNew")
        agent.state_repo.get_state.return_value = ("hashOld", "Result")
        
        run, h, out = agent.check_freshness(context)
        assert run is True
        assert h == "hashNew"

    def test_update_state(self, agent):
        agent.update_state("hash123", "Output", "key")
        agent.state_repo.save_state.assert_called_with("TestAgent_key", "TestAgent", "hash123", "Output")

    @pytest.mark.asyncio
    async def test_call_real_llm_openrouter(self, agent):
        """Test _call_real_llm delegates through gateway (via call_llm)."""
        agent.config = {"provider": "OpenRouter", "api_key": "sk-123", "model": "gpt-4"}
        # Patch the gateway directly since _call_real_llm now bridges to call_llm -> gateway
        from unittest.mock import AsyncMock
        mock_gw = MagicMock()
        mock_gw.chat = AsyncMock(return_value="Hello OpenRouter")
        agent._llm_gateway = mock_gw
            
        resp = await agent._call_real_llm("hi", "sys")
        assert resp == "Hello OpenRouter"
            
    @pytest.mark.asyncio
    async def test_call_real_llm_gemini(self, agent):
        """Test _call_real_llm delegates through gateway (via call_llm)."""
        agent.config = {"provider": "Google Gemini", "api_key": "sk-123", "model": "gemini-pro"}
        from unittest.mock import AsyncMock
        mock_gw = MagicMock()
        mock_gw.chat = AsyncMock(return_value="Hello Gemini")
        agent._llm_gateway = mock_gw
            
        resp = await agent._call_real_llm("hi", "sys")
        assert resp == "Hello Gemini"

    @pytest.mark.asyncio
    async def test_call_real_llm_openai(self, agent):
        """Test _call_real_llm delegates through gateway (via call_llm)."""
        agent.config = {"provider": "OpenAI", "api_key": "sk-123", "model": "gpt-4"}
        from unittest.mock import AsyncMock
        mock_gw = MagicMock()
        mock_gw.chat = AsyncMock(return_value="Hello OpenAI")
        agent._llm_gateway = mock_gw
            
        resp = await agent._call_real_llm("hi", "sys")
        assert resp == "Hello OpenAI"

    @pytest.mark.asyncio
    async def test_call_real_llm_fail(self, agent):
        """Test _call_real_llm propagates gateway errors."""
        agent.config = {"provider": "Google Gemini", "api_key": "sk-123", "model": "gemini-pro"}
        from unittest.mock import AsyncMock
        mock_gw = MagicMock()
        mock_gw.chat = AsyncMock(side_effect=Exception("Net Error"))
        agent._llm_gateway = mock_gw
        with pytest.raises(Exception):
             await agent._call_real_llm("hi", "sys")

    def test_render_user_context_json(self, agent):
        ctx = {"a": 1}
        res = agent._render_user_context(ctx)
        assert '"a": 1' in res

    def test_render_system_prompt_jinja(self, agent):
        agent.system_prompt = "Hello {{ name }}"
        res = agent.render_system_prompt({"name": "World"})
        assert res == "Hello World"

    @pytest.mark.asyncio
    async def test_run_tool_loop_search(self, agent):
        # Mock Search Service import
        with patch('src.services.search_service.InternetSearchService') as MockSearch:
             mock_search_instance = MockSearch.return_value
             mock_search_instance.search_financial_context.return_value = [{"title": "T", "snippet": "S", "link": "L"}]
             
             # Mock call_llm to first return SEARCH command, then Final Answer
             from unittest.mock import AsyncMock
             agent.call_llm = AsyncMock(side_effect=[
                 'SEARCH: "Apple Stock"',
                 'Final Answer: Apple is up.'
             ])
             
             from unittest.mock import AsyncMock
             mock_search_instance.search_financial_context = AsyncMock(return_value=[{"title": "T", "snippet": "S", "link": "L"}])
             
             resp = await agent.run_tool_loop({})
             
             assert resp == 'Final Answer: Apple is up.'
             assert agent.call_llm.call_count == 2
             mock_search_instance.search_financial_context.assert_called_with("Apple Stock", max_results=3)

