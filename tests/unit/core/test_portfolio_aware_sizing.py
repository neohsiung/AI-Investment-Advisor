"""
Tests for Position Sizing Skills.
"""
import pytest
import unittest
from unittest.mock import MagicMock, patch



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
