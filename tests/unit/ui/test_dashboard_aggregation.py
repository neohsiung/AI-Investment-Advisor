import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import os
import pandas as pd

sys.path.append(os.getcwd())

from src.services.dashboard_service import DashboardService
from src.domain.trading import Position, Account, BrokerType

class TestDashboardAggregation:
    def setup_method(self):
        # Mock Dependencies
        self.mock_transaction_service = MagicMock()
        self.mock_transaction_service.get_transactions.return_value = pd.DataFrame()
        
        # Streamlit is centrally mocked in conftest.py
        self.mock_market_data = MagicMock()
        self.mock_market_data.get_current_prices.return_value = {"AAPL": 150.0}

        # Mock Aggregator — get_aggregated_portfolio is async, use AsyncMock
        self.aggregator_patcher = patch('src.services.portfolio_aggregator_service.PortfolioAggregatorService')
        self.MockAggregator = self.aggregator_patcher.start()
        
        self.mock_agg_instance = MagicMock()
        self.MockAggregator.return_value = self.mock_agg_instance
        
        self.mock_agg_instance.get_aggregated_portfolio = AsyncMock(return_value={
            "total_equity": 50000.0,
            "total_cash": 20000.0,
            "positions": [
                Position("AAPL", 10, 140, 150, 1500, 100)
            ],
            "broker_breakdown": {
                "etoro": Account(BrokerType.ETORO, "e1", 25000, 10000),
                "ibkr": Account(BrokerType.IBKR, "i1", 25000, 10000)
            }
        })
        
        # Patch update_daily_snapshot
        self.snapshot_patcher = patch('src.services.dashboard_service.update_daily_snapshot')
        self.mock_snapshot = self.snapshot_patcher.start()

    def teardown_method(self):
        self.aggregator_patcher.stop()
        self.snapshot_patcher.stop()

    @pytest.mark.asyncio
    async def test_prepare_dashboard_data_uses_aggregator(self):
        # Initialize Service with mocked repos
        service = DashboardService(user_id="user1", db_path=":memory:")
        service.transaction_service = self.mock_transaction_service
        service.market_service = self.mock_market_data
        # _fetch_market_prices is async
        service._fetch_market_prices = AsyncMock(return_value={"AAPL": 150.0})
        
        # Inject mocks for analytics engines which might try to connect to DB
        service.calc = MagicMock()
        # NLV calc logic: cash_balance + invested_capital + unrealized_pnl
        # Expected: 20000 + 1500 + 0 = 21500
        service.calc.calculate_metrics.return_value = {
            'nlv': 21500.0,
            'cash_balance': 20000.0,
            'leverage_ratio': 1.0,
            'tnv': 1500.0
        }
        service.pnl_calc = MagicMock()
        service.pnl_calc.calculate_breakdown.return_value = {
            'invested_capital': 1500.0,
            'unrealized': 0.0,
            'realized': 0.0
        }
        service.roi_engine = MagicMock()
        service.roi_engine.calculate_roi.return_value = 5.0

        # prepare_dashboard_data is async
        data = await service.prepare_dashboard_data("user1")
        
        # Verify Metrics — NLV comes from broker accounts (authoritative source)
        # etoro: 25000 + ibkr: 25000 = 50000
        metrics = data['metrics']
        assert metrics['nlv'] == 50000.0
        # Cash: etoro 10000 + ibkr 10000 = 20000
        assert metrics['cash_balance'] == 20000.0
        
        # Verify Positions
        positions_df = data['positions_df']
        assert not positions_df.empty
        assert len(positions_df) == 1
        assert positions_df.iloc[0]['ticker'] == 'AAPL'
        
        # Verify Broker Breakdown passed through
        assert 'etoro' in data['broker_breakdown']
