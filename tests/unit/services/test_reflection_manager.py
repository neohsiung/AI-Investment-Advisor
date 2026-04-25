import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.reflection_manager import ReflectionManager
from src.domain.interfaces import LLMConfig

class TestReflectionManager:
    @pytest.fixture
    def mock_deps(self):
        with patch("src.services.reflection_manager.SettingsService") as m_settings, \
             patch("src.services.reflection_manager.TokenLoggerService") as m_tokens, \
             patch("src.services.reflection_manager.BudgetAwareModelRouter") as m_router, \
             patch("src.services.reflection_manager.EvolutionMetrics") as m_metrics, \
             patch("src.services.reflection_manager.LLMGatewayFactory") as m_factory, \
             patch("src.services.reflection_manager.LoggingLLMGateway") as m_logging_gw:
            
            # Make the chat method async
            m_logging_gw.return_value.chat = AsyncMock()
            
            yield {
                "settings": m_settings.return_value,
                "tokens": m_tokens.return_value,
                "router": m_router.return_value,
                "metrics": m_metrics.return_value,
                "factory": m_factory,
                "logging_gw": m_logging_gw.return_value
            }

    @pytest.mark.asyncio
    async def test_reflect_normal_budget(self, mock_deps):
        # Setup
        mock_deps["router"].is_budget_critical.return_value = False
        mock_deps["router"].get_config.return_value = LLMConfig(provider="OpenRouter", model="gpt-4o-mini")
        
        mock_llm = MagicMock()
        mock_deps["factory"].create.return_value = mock_llm
        
        # Mocking the logging gateway to return a JSON response
        mock_deps["logging_gw"].chat = AsyncMock(return_value=json.dumps({
            "recommended_action": "retry",
            "reasoning": "Test reasoning",
            "corrected_args": {"query": "fixed"}
        }))
        
        manager = ReflectionManager(user_id="test_user")
        result = await manager.reflect_on_error("SEARCH", {"query": "bad"}, "Error 404")
        
        assert result["recommended_action"] == "retry"
        assert result["corrected_args"]["query"] == "fixed"
        
        # Verify metrics recorded
        mock_deps["metrics"].record_reflection_event.assert_called_once()
        args, kwargs = mock_deps["metrics"].record_reflection_event.call_args
        assert kwargs["success"] is True
        assert kwargs["action"] == "retry"

    @pytest.mark.asyncio
    async def test_reflect_critical_budget(self, mock_deps):
        # Setup
        mock_deps["router"].is_budget_critical.return_value = True
        mock_deps["router"].get_config.return_value = LLMConfig(provider="OpenRouter", model="gpt-4o-mini")
        
        mock_deps["logging_gw"].chat = AsyncMock(return_value=json.dumps({
            "recommended_action": "fail",
            "reasoning": "Too expensive"
        }))
        
        manager = ReflectionManager(user_id="test_user")
        
        with patch("src.services.reflection_manager.ReflectionPrompt.build_compressed") as m_compressed:
            m_compressed.return_value = "Compressed Prompt"
            result = await manager.reflect_on_error("SEARCH", {}, "Error")
            
            m_compressed.assert_called_once()
            assert result["recommended_action"] == "fail"

    @pytest.mark.asyncio
    async def test_reflect_llm_failure(self, mock_deps):
        # Setup
        mock_deps["router"].is_budget_critical.return_value = False
        mock_deps["router"].get_config.return_value = LLMConfig(provider="OpenRouter", model="gpt-4o-mini")
        
        # LLM raises exception
        mock_deps["logging_gw"].chat = AsyncMock(side_effect=Exception("LLM Down"))
        
        manager = ReflectionManager(user_id="test_user")
        result = await manager.reflect_on_error("SEARCH", {}, "Error")
        
        assert result is None
        
        # Verify metrics recorded as failure
        mock_deps["metrics"].record_reflection_event.assert_called_once()
        args, kwargs = mock_deps["metrics"].record_reflection_event.call_args
        assert kwargs["success"] is False
        assert kwargs["action"] == "none"
