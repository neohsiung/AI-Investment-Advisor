"""
Test for LLM Tier Fallback Logic.
驗證 LLM 分流層降級與回退邏輯，確保在沒有資料庫綁定時正確回退至使用者設定。
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter
from src.agents.base_agent import BaseAgent
from src.infrastructure.llm.tier_config import TierConfig

@pytest.fixture
def mock_settings_service():
    service = MagicMock()
    # Default: no model settings
    service.get_all_settings.return_value = {}
    service.get_setting.side_effect = lambda k, d=None, uid=None: d
    return service

@pytest.fixture
def mock_token_logger():
    logger = MagicMock()
    logger.get_user_spending.return_value = {"total_cost": 0.0}
    return logger

class TestTierFallbackLogic:
    
    @patch('src.repositories.llm_tier_binding_repository.LLMTierBindingRepository')
    def test_get_config_chain_empty_when_no_binding(self, mock_repo_class, mock_settings_service, mock_token_logger):
        """Verify that get_config_chain returns empty list when DB binding is missing."""
        mock_repo = mock_repo_class.return_value
        mock_repo.get_by_tier.return_value = None
        
        router = BudgetAwareModelRouter(mock_settings_service, mock_token_logger)
        chain = router.get_config_chain(user_id="test_user", tier="smart")
        
        assert chain == []

    @patch('src.repositories.llm_tier_binding_repository.LLMTierBindingRepository')
    def test_base_agent_fallback_to_legacy_settings(self, mock_repo_class, mock_settings_service, mock_token_logger):
        """Verify that BaseAgent correctly falls back to Settings Table when Chain is empty."""
        # 1. Setup DB Repository to return nothing
        mock_repo = mock_repo_class.return_value
        mock_repo.get_by_tier.return_value = None
        
        # 2. Setup Settings Service to have "legacy" settings
        mock_settings_service.get_all_settings.return_value = {
            "AI_MODEL_SMART": "google/gemini-2.0-pro-exp",
            "AI_PROVIDER": "OpenRouter",
            "API_KEY": "test-key"
        }
        
        # 3. Initialize Agent
        from src.agents.base_agent import BaseAgent
        class TestAgent(BaseAgent):
            async def run(self, context, mode=None): return "ok"
            
        # We need to ensure BaseAgent uses our mocked dependencies
        with patch('src.agents.base_agent.SettingsService', return_value=mock_settings_service), \
             patch('src.agents.base_agent.TokenLoggerService', return_value=mock_token_logger), \
             patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Test Prompt"):
            
            agent = TestAgent(
                name="TestSmartAgent",
                tier="smart",
                user_id="test_user",
                prompt_path="dummy",
            )
            config = agent._load_config()
            
            # 4. Verify config resolved to the legacy setting
            assert config["model"] == "google/gemini-2.0-pro-exp"
            assert config["provider"] == "OpenRouter"
            assert config["api_key"] == "test-key"

    def test_fallback_eligible_error_mapping(self):
        """Verify that 404 is still classified as MODEL_NOT_FOUND (eligible for fallback)."""
        from httpx import Response, HTTPStatusError, Request
        from src.infrastructure.llm.error_classifier import classify_error, ErrorCategory, should_fallback
        
        # Simulate a 404 response
        request = Request("POST", "https://api.openrouter.ai/api/v1/chat/completions")
        response = Response(404, request=request)
        error = HTTPStatusError("404 Not Found", request=request, response=response)
        
        category = classify_error(error)
        is_eligible = should_fallback(category)
        
        assert category == ErrorCategory.MODEL_NOT_FOUND
        assert is_eligible is True
