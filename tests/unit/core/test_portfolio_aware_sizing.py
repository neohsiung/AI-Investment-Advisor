"""
Tests for ActionExtractorAgent with portfolio context support.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.action_extractor import ActionExtractorAgent


@pytest.fixture
def extractor_agent():
    """Create an ActionExtractorAgent with mocked LLM."""
    with patch.object(ActionExtractorAgent, '_load_prompt', return_value="Test"):
        agent = ActionExtractorAgent(use_cache=False, user_id="test_user", tier="fast")
    return agent


class TestActionExtractorDictContext:
    """Test that ActionExtractor correctly handles dict context with portfolio."""

    @pytest.mark.asyncio
    async def test_accepts_dict_context(self, extractor_agent):
        """Should accept dict with decision_text and portfolio keys."""
        mock_response = '[{"ticker": "TSLA", "action": "SELL", "quantity": 0.5, "confidence": 8, "intent": "full_close", "reason": "Exit position"}]'
        
        with patch.object(extractor_agent, 'run_tool_loop', new_callable=AsyncMock, return_value=mock_response):
            result = await extractor_agent.run({
                "decision_text": "We should exit TSLA entirely",
                "portfolio": "TSLA(0.5), NVDA(10)"
            })
        
        assert len(result) == 1
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["action"] == "SELL"
        assert result[0]["quantity"] == 0.5
        assert result[0].get("intent") == "full_close"

    @pytest.mark.asyncio
    async def test_accepts_legacy_string_context(self, extractor_agent):
        """Should accept a plain string (backward compatible)."""
        mock_response = '[{"ticker": "AAPL", "action": "BUY", "quantity": 100, "confidence": 7, "reason": "Good value"}]'
        
        with patch.object(extractor_agent, 'run_tool_loop', new_callable=AsyncMock, return_value=mock_response):
            result = await extractor_agent.run("We should buy AAPL at current levels")
        
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_empty_context_returns_empty(self, extractor_agent):
        """Empty or None context should return empty list."""
        assert await extractor_agent.run(None) == []
        assert await extractor_agent.run("") == []
        assert await extractor_agent.run({}) == []
        assert await extractor_agent.run({"decision_text": ""}) == []

    @pytest.mark.asyncio
    async def test_portfolio_injected_into_prompt(self, extractor_agent):
        """When portfolio is provided, it should appear in the prompt sent to LLM."""
        captured_prompt = None
        
        async def capture_prompt(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return '[]'
        
        with patch.object(extractor_agent, 'run_tool_loop', side_effect=capture_prompt):
            await extractor_agent.run({
                "decision_text": "Hold all positions",
                "portfolio": "TSLA(0.5), NVDA(10), Cash: $2,500"
            })
        
        assert captured_prompt is not None
        assert "TSLA(0.5)" in captured_prompt
        assert "NVDA(10)" in captured_prompt
        assert "PORTFOLIO HOLDINGS" in captured_prompt

    @pytest.mark.asyncio
    async def test_no_portfolio_no_holdings_block(self, extractor_agent):
        """When no portfolio is provided, PORTFOLIO HOLDINGS block should not appear."""
        captured_prompt = None
        
        async def capture_prompt(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return '[]'
        
        with patch.object(extractor_agent, 'run_tool_loop', side_effect=capture_prompt):
            await extractor_agent.run("Just a simple decision text")
        
        assert captured_prompt is not None
        assert "PORTFOLIO HOLDINGS" not in captured_prompt

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self, extractor_agent):
        """Invalid LLM JSON response should return empty list, not crash."""
        with patch.object(extractor_agent, 'run_tool_loop', new_callable=AsyncMock, return_value="This is not JSON"):
            result = await extractor_agent.run("Some decision text")
        
        assert result == []


class TestPositionSizingSkill:
    """Test the position_sizing skill implementation in registry."""

    def test_skill_sell_clamps_to_holding(self):
        """SELL with quantity > holding should be clamped."""
        from src.agents.skills.registry import _position_sizing
        import json

        mock_account = MagicMock()
        mock_account.total_equity = 10000
        mock_account.available_cash = 5000

        mock_pos = MagicMock()
        mock_pos.symbol = "TSLA"
        mock_pos.quantity = 0.5

        mock_broker = MagicMock()
        mock_broker.get_account.return_value = mock_account
        mock_broker.get_positions.return_value = [mock_pos]

        mock_settings = MagicMock()
        mock_settings.get.return_value = None  # Use defaults

        with patch('src.services.broker_factory.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.repositories.settings_repository.AlchemySettingsRepository', return_value=mock_settings):
            result_json = _position_sizing("test_user", "TSLA", "SELL", desired_quantity=1.0)
        
        result = json.loads(result_json)
        assert result["recommended_quantity"] == 0.5
        assert "Clamped" in result["reason"]

    def test_skill_sell_no_holding_returns_zero(self):
        """SELL with no holding should return 0."""
        from src.agents.skills.registry import _position_sizing
        import json

        mock_account = MagicMock()
        mock_account.total_equity = 10000
        mock_account.available_cash = 5000

        mock_broker = MagicMock()
        mock_broker.get_account.return_value = mock_account
        mock_broker.get_positions.return_value = []

        mock_settings = MagicMock()
        mock_settings.get.return_value = None

        with patch('src.services.broker_factory.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.repositories.settings_repository.AlchemySettingsRepository', return_value=mock_settings):
            result_json = _position_sizing("test_user", "TSLA", "SELL", desired_quantity=1.0)
        
        result = json.loads(result_json)
        assert result["recommended_quantity"] == 0
        assert "No active position" in result["reason"]

    def test_skill_full_close_intent(self):
        """SELL with intent=full_close should return full holding."""
        from src.agents.skills.registry import _position_sizing
        import json

        mock_account = MagicMock()
        mock_account.total_equity = 10000
        mock_account.available_cash = 5000

        mock_pos = MagicMock()
        mock_pos.symbol = "NVDA"
        mock_pos.quantity = 10.0

        mock_broker = MagicMock()
        mock_broker.get_account.return_value = mock_account
        mock_broker.get_positions.return_value = [mock_pos]

        mock_settings = MagicMock()
        mock_settings.get.return_value = None

        with patch('src.services.broker_factory.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.repositories.settings_repository.AlchemySettingsRepository', return_value=mock_settings):
            result_json = _position_sizing("test_user", "NVDA", "SELL", desired_quantity=5.0, intent="full_close")
        
        result = json.loads(result_json)
        assert result["recommended_quantity"] == 10.0
        assert "Full close" in result["reason"]
