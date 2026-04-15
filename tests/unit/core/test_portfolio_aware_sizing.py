"""
Tests for Position Sizing Skills.
"""
import pytest
import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import io

from src.agents.skills.position_sizing.cli import main

class TestPositionSizingSkill:
    """Test the position_sizing cli implementation."""

    def test_skill_sell_clamps_to_holding(self):
        """SELL with quantity > holding should be clamped."""
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

        mock_args = ["cli.py", "--user_id", "test_user", "--ticker", "TSLA", "--action", "SELL", "--desired_quantity", "1.0"]

        with patch('src.agents.skills.position_sizing.cli.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.agents.skills.position_sizing.cli.AlchemySettingsRepository', return_value=mock_settings), \
             patch.object(sys, 'argv', mock_args), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            main()
        
        output = mock_stdout.getvalue().strip()
        result = json.loads(output)
        assert result["recommended_quantity"] == 0.5
        assert "Clamped" in result["reason"]

    def test_skill_sell_no_holding_returns_zero(self):
        """SELL with no holding should return 0."""
        mock_account = MagicMock()
        mock_account.total_equity = 10000
        mock_account.available_cash = 5000

        mock_broker = MagicMock()
        mock_broker.get_account.return_value = mock_account
        mock_broker.get_positions.return_value = []

        mock_settings = MagicMock()
        mock_settings.get.return_value = None

        mock_args = ["cli.py", "--user_id", "test_user", "--ticker", "TSLA", "--action", "SELL", "--desired_quantity", "1.0"]

        with patch('src.agents.skills.position_sizing.cli.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.agents.skills.position_sizing.cli.AlchemySettingsRepository', return_value=mock_settings), \
             patch.object(sys, 'argv', mock_args), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            main()
        
        output = mock_stdout.getvalue().strip()
        result = json.loads(output)
        assert result["recommended_quantity"] == 0
        assert "No active position" in result["reason"]

    def test_skill_full_close_intent(self):
        """SELL with intent=full_close should return full holding."""
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

        mock_args = ["cli.py", "--user_id", "test_user", "--ticker", "NVDA", "--action", "SELL", "--desired_quantity", "5.0", "--intent", "full_close"]

        with patch('src.agents.skills.position_sizing.cli.BrokerFactory.get_broker', return_value=mock_broker), \
             patch('src.agents.skills.position_sizing.cli.AlchemySettingsRepository', return_value=mock_settings), \
             patch.object(sys, 'argv', mock_args), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            main()
        
        output = mock_stdout.getvalue().strip()
        result = json.loads(output)
        assert result["recommended_quantity"] == 10.0
        assert "Full close" in result["reason"]
