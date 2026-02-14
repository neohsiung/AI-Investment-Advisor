
import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.getcwd())

from src.services.portfolio_aggregator_service import PortfolioAggregatorService
from src.domain.trading import Position, Account, BrokerType

class TestPortfolioAggregator(unittest.TestCase):
    def setUp(self):
        # Mock Brokers
        self.etoro = MagicMock()
        self.etoro.get_account.return_value = Account(BrokerType.ETORO, "e1", 10000, 5000)
        self.etoro.get_positions.return_value = [
            Position("AAPL", 10, 150, 160, 1600, 100),
            Position("TSLA", 5, 200, 210, 1050, 50)
        ]

        self.futu = MagicMock()
        self.futu.get_account.return_value = Account(BrokerType.FUTU, "f1", 20000, 10000)
        self.futu.get_positions.return_value = [
            Position("AAPL", 5, 140, 160, 800, 100), # Overlap with Etoro
            Position("NVDA", 2, 500, 550, 1100, 100)
        ]

        # Patch Factory to return mocks
        self.factory_patcher = unittest.mock.patch('src.services.broker_factory.BrokerFactory.get_enabled_brokers')
        self.mock_get_brokers = self.factory_patcher.start()
        self.mock_get_brokers.return_value = {"etoro": self.etoro, "futu": self.futu}
        
    def tearDown(self):
        self.factory_patcher.stop()

    def test_aggregation(self):
        aggregator = PortfolioAggregatorService("user1")
        data = aggregator.get_aggregated_portfolio()
        
        # Verify Totals
        self.assertEqual(data['total_equity'], 30000)
        self.assertEqual(data['total_cash'], 15000)
        
        # Verify Positions
        positions = data['positions']
        self.assertEqual(len(positions), 3) # AAPL, TSLA, NVDA
        
        # Verify AAPL Merge
        aapl = next(p for p in positions if p.symbol == "AAPL")
        self.assertEqual(aapl.quantity, 15) # 10 + 5
        self.assertAlmostEqual(aapl.market_value, 2400) # 1600 + 800
        
        # Verify Average Price
        # (10*150 + 5*140) / 15 = (1500 + 700) / 15 = 2200 / 15 = 146.66...
        self.assertAlmostEqual(aapl.open_price, 146.666666, places=2)

if __name__ == '__main__':
    unittest.main()
