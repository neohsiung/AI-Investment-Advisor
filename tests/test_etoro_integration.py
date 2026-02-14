
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

class TestEtoroIntegration(unittest.TestCase):
    def setUp(self):
        self.service = EtoroService(base_url="http://mock-etoro", mode="demo")
        # Mock Internal Repos via RiskManager
        self.service.risk_manager.transaction_repo = MagicMock()
        self.service.risk_manager.settings_repo = MagicMock()
        
        # Default Settings
        self.service.risk_manager.settings_repo.get.side_effect = lambda uid, k, default=None: "true" if k == "ai_trading_enabled" else default

    def test_check_constraints_ok(self):
        # Mock transaction count on RiskManager
        self.service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
        self.service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=False)
        
        # Test directly on Risk Manager
        result = self.service.risk_manager.check_constraints("user1")
        self.assertTrue(result)

    def test_check_constraints_max_daily(self):
        # Mock on RiskManager
        self.service.risk_manager._get_daily_trade_count = MagicMock(return_value=10)
        result = self.service.risk_manager.check_constraints("user1")
        self.assertFalse(result)

    def test_circuit_breaker_trigger(self):
        # Mock on RiskManager
        self.service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
        self.service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=True)
        
        result = self.service.risk_manager.check_constraints("user1")
        self.assertFalse(result)
        
        # Check disable
        self.service.risk_manager.settings_repo.set.assert_called_with("user1", "ai_trading_enabled", "false")

    @patch('src.services.etoro_service.requests.get')
    def test_sync_history(self, mock_get):
        # Mock Etoro History Response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"Instrument": "AAPL", "OpenDateTime": "2025-01-01T10:00:00", "Action": "Buy", "Amount": 100, "OpenRate": 150}
        ]
        mock_get.return_value = mock_response
        self.service.transaction_repo = MagicMock()
        self.service.transaction_repo.get_all_by_user.return_value = []
        
        # Test Sync
        res = self.service.sync_history("user1")
        self.assertEqual(res['added'], 1)
        self.service.transaction_repo.add.assert_called_once()
        
    def test_execute_order_wraps_risk(self):
        # Test that execute_order checks risk
        self.service.risk_manager.check_constraints = MagicMock(return_value=False)
        order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=100)
        
        res = self.service.execute_order(order)
        self.assertEqual(res['status'], 'failed')
        self.assertIn("Risk Manager", res['reason'])

if __name__ == '__main__':
    unittest.main()
