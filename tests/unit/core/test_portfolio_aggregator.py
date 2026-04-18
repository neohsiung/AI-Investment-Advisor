
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
import os

sys.path.append(os.getcwd())

from src.services.portfolio_aggregator_service import PortfolioAggregatorService
from src.domain.trading import Position, Account, BrokerType

class TestPortfolioAggregator:
    def setup_method(self):
        # Mock Brokers — get_account is async, use AsyncMock
        self.etoro = MagicMock()
        self.etoro.get_account = AsyncMock(return_value=Account(BrokerType.ETORO, "e1", 10000, 5000))
        self.etoro.get_positions = AsyncMock(return_value=[
            Position("AAPL", 10, 150, 160, 1600, 100),
            Position("TSLA", 5, 200, 210, 1050, 50)
        ])

        self.ibkr = MagicMock()
        self.ibkr.get_account = AsyncMock(return_value=Account(BrokerType.IBKR, "i1", 20000, 10000))
        self.ibkr.get_positions = AsyncMock(return_value=[
            Position("AAPL", 5, 140, 160, 800, 100), # Overlap with Etoro
            Position("NVDA", 2, 500, 550, 1100, 100)
        ])

    @pytest.mark.asyncio
    async def test_aggregation(self):
        # Patch Factory to return mocks
        with __import__('unittest.mock', fromlist=['patch']).patch(
            'src.services.broker_factory.BrokerFactory.get_enabled_brokers',
            return_value={"etoro": self.etoro, "ibkr": self.ibkr}
        ):
            aggregator = PortfolioAggregatorService("user1")
            data = await aggregator.get_aggregated_portfolio()
            
            # Verify Totals
            assert data['total_equity'] == 30000
            assert data['total_cash'] == 15000
            
            # Verify Positions
            positions = data['positions']
            assert len(positions) == 3  # AAPL, TSLA, NVDA
            
            # Verify AAPL Merge
            aapl = next(p for p in positions if p.symbol == "AAPL")
            assert aapl.quantity == 15  # 10 + 5
            assert abs(aapl.market_value - 2400) < 0.01  # 1600 + 800
            
            # Verify Average Price
            # (10*150 + 5*140) / 15 = (1500 + 700) / 15 = 2200 / 15 = 146.66...
            assert abs(aapl.open_price - 146.666666) < 0.01
