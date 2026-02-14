
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pandas as pd

sys.path.append(os.getcwd())

from src.services.dashboard_service import DashboardService
from src.domain.trading import Position, Account, BrokerType

class TestDashboardAggregation(unittest.TestCase):
    def setUp(self):
        # Mock Dependencies
        self.mock_transaction_service = MagicMock()
        self.mock_transaction_service.get_transactions.return_value = pd.DataFrame()
        
        self.mock_market_data = MagicMock()
        self.mock_market_data.get_current_prices.return_value = {"AAPL": 150.0}

        # Mock Aggregator
        self.aggregator_patcher = patch('src.services.portfolio_aggregator_service.PortfolioAggregatorService')
        self.MockAggregator = self.aggregator_patcher.start()
        
        self.mock_agg_instance = MagicMock()
        self.MockAggregator.return_value = self.mock_agg_instance
        
        self.mock_agg_instance.get_aggregated_portfolio.return_value = {
            "total_equity": 50000.0,
            "total_cash": 20000.0,
            "positions": [
                Position("AAPL", 10, 140, 150, 1500, 100)
            ],
            "broker_breakdown": {
                "etoro": Account(BrokerType.ETORO, "e1", 25000, 10000),
                "futu": Account(BrokerType.FUTU, "f1", 25000, 10000)
            }
        }
        
        # Patch update_daily_snapshot
        self.snapshot_patcher = patch('src.services.dashboard_service.update_daily_snapshot')
        self.mock_snapshot = self.snapshot_patcher.start()

    def tearDown(self):
        self.aggregator_patcher.stop()
        self.snapshot_patcher.stop()

    def test_prepare_dashboard_data_uses_aggregator(self):
        # Initialize Service with mocked repos
        service = DashboardService(db_path=":memory:")
        service.transaction_service = self.mock_transaction_service
        service.market_service = self.mock_market_data
        
        # Inject mocks for analytics engines which might try to connect to DB
        service.calc = MagicMock()
        service.calc.calculate_metrics.return_value = {'nlv': 0, 'leverage_ratio': 1.0}
        service.pnl_calc = MagicMock()
        service.pnl_calc.calculate_breakdown.return_value = {}
        service.roi_engine = MagicMock()
        service.roi_engine.calculate_roi.return_value = 5.0

        data = service.prepare_dashboard_data("user1")
        
        # Verify Metrics Overridden
        metrics = data['metrics']
        self.assertEqual(metrics['nlv'], 50000.0)
        self.assertEqual(metrics['cash_balance'], 20000.0)
        
        # Verify Positions
        positions_df = data['positions_df']
        self.assertFalse(positions_df.empty)
        self.assertEqual(len(positions_df), 1)
        self.assertEqual(positions_df.iloc[0]['ticker'], 'AAPL')
        
        # Verify Broker Breakdown passed through
        self.assertIn('etoro', data['broker_breakdown'])

if __name__ == '__main__':
    unittest.main()
