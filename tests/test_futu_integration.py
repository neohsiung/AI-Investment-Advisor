
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

# Add project root to path
sys.path.append(os.getcwd())

# Mock futu module BEFORE importing service
from tests.mocks import futu as mock_futu
sys.modules['futu'] = mock_futu

from src.services.futu_service import FutuService
from src.domain.trading import Order, OrderAction

class TestFutuIntegration(unittest.TestCase):
    def setUp(self):
        # We don't need to patch FUTU_AVAILABLE because import should succeed now
        
        self.service = FutuService(host="127.0.0.1", port=11111, is_sim=True)
        # Mock Risk Manager
        self.service.risk_manager = MagicMock()
        self.service.risk_manager.check_constraints.return_value = True
        
        # Inject Mock Contexts
        self.service.trd_ctx = MagicMock()

    def tearDown(self):
        # Clean up sys.modules if needed, but safe to leave mock for this process
        pass

    def test_get_account(self):
        # Mock AccInfo Query
        mock_df = pd.DataFrame({
            'currency': ['USD'],
            'total_assets': [10000.0],
            'cash': [5000.0],
            'acc_id': ['123456']
        })
        # Return tuple (RET_OK, data)
        self.service.trd_ctx.accinfo_query.return_value = (0, mock_df)
        
        account = self.service.get_account()
        self.assertIsNotNone(account)
        self.assertEqual(account.total_equity, 10000.0)
        self.assertEqual(account.available_cash, 5000.0)
        self.assertEqual(account.currency, 'USD')

    def test_get_positions(self):
        # Mock Position Query
        mock_df = pd.DataFrame({
            'code': ['US.AAPL'],
            'qty': [10.0],
            'cost_price': [150.0],
            'nominal_price': [160.0],
            'market_val': [1600.0],
            'pl_val': [100.0]
        })
        self.service.trd_ctx.position_list_query.return_value = (0, mock_df)
        
        positions = self.service.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].symbol, 'US.AAPL')
        self.assertEqual(positions[0].unrealized_pnl, 100.0)

    def test_execute_order(self):
        # Mock Place Order
        mock_df = pd.DataFrame({'order_id': ['987654']})
        self.service.trd_ctx.place_order.return_value = (0, mock_df)
        
        order = Order(symbol="US.TSLA", action=OrderAction.BUY, quantity=5)
        res = self.service.execute_order(order)
        
        self.assertEqual(res['status'], 'executed')
        self.assertEqual(res['order_id'], '987654')
        self.service.trd_ctx.place_order.assert_called_once()

    def test_sync_history(self):
        # Mock History Query
        mock_df = pd.DataFrame({
            'code': ['US.NVDA'],
            'updated_time': ['2025-02-14 10:00:00'],
            'trd_side': ['BUY'],
            'dealt_qty': [20.0],
            'dealt_avg_price': [500.0]
        })
        self.service.trd_ctx.history_order_list_query.return_value = (0, mock_df)
        
        # Mock Repo
        self.service.transaction_repo = MagicMock()
        self.service.transaction_repo.get_all_by_user.return_value = []
        
        res = self.service.sync_history("user1")
        self.assertEqual(res['added'], 1)
        self.service.transaction_repo.add.assert_called_once()

if __name__ == '__main__':
    unittest.main()
