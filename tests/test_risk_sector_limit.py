
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.append(os.getcwd())

from src.infrastructure.risk_manager import RiskManager
from src.domain.trading import Position

class TestRiskSectorLimit(unittest.TestCase):
    def setUp(self):
        self.risk_manager = RiskManager()
        
        # Mock Settings
        self.risk_manager.settings_repo = MagicMock()
        self.risk_manager.settings_repo.get.side_effect = lambda uid, key, default=None: {
            "risk_max_sector_exposure": "0.30",
            "ai_trading_enabled": "true"
        }.get(key, default)
        
        # Mock Market Data Service (via import inside method)
        self.mds_patcher = patch('src.services.market_data_service.MarketDataService')
        self.MockMDS = self.mds_patcher.start()
        self.mock_mds_instance = MagicMock()
        self.MockMDS.return_value = self.mock_mds_instance
        
        # Define Sector Map
        self.sector_map = {
            "AAPL": "Technology",
            "MSFT": "Technology",
            "NVDA": "Technology",
            "XOM": "Energy",
            "CVX": "Energy",
            "JPM": "Financial"
        }
        
        def get_financials(ticker):
            return {"sector": self.sector_map.get(ticker, "Unknown")}
            
        self.mock_mds_instance.get_financials.side_effect = get_financials

    def tearDown(self):
        self.mds_patcher.stop()

    def test_sector_exposure_limit(self):
        # 1. Setup Portfolio: $70k Total. $20k Tech (AAPL).
        # Exposure: 20/70 = 28.5%. Limit: 30%.
        positions = [
            Position("AAPL", 200, 100, 100, 20000, 0), # Tech
            Position("XOM", 500, 100, 100, 50000, 0)   # Energy
        ]
        
        # 2. Test: Buy More Tech (MSFT $5000)
        # New Total: 75k. New Tech: 25k. 
        # Exposure: 25/75 = 33.3%. > 30%. Should FAIL.
        res = self.risk_manager.check_sector_exposure("user1", "MSFT", 5000, positions)
        self.assertFalse(res, "Should block trade exceeding sector limit")

        # 3. Test: Buy Financial (JPM $5000)
        # New Total: 75k. Fin: 5k. Tech: 20k. Energy: 50k.
        # All below 30%? Energy is 50/75 = 66%. BUT we are checking the NEW ticker's sector.
        # Although Energy is over-exposed, we are adding to Financial. 
        # The logic usually checks if the *Trade's Sector* is over limit.
        # If I buy JPM, Financial exposure becomes 5/75 = 6.6%. OK.
        # Does the logic block *any* trade if *another* sector is over? 
        # My implementation only checks `new_sector` exposure.
        res = self.risk_manager.check_sector_exposure("user1", "JPM", 5000, positions)
        self.assertTrue(res, "Should allow trade in under-exposed sector")

    def test_kill_switch(self):
        self.risk_manager.trigger_kill_switch("user1")
        self.risk_manager.settings_repo.set.assert_called_with("user1", "ai_trading_enabled", "false")

if __name__ == '__main__':
    unittest.main()
