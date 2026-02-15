
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from src.infrastructure.risk_manager import RiskManager
from src.services.analytics_service import AnalyticsService, PnLCalculator, update_daily_snapshot

class TestCoverageFinalPush:
    
    @pytest.fixture
    def risk_manager(self):
        with patch('src.infrastructure.risk_manager.SqliteTransactionRepository'), \
             patch('src.infrastructure.risk_manager.SqliteSettingsRepository'):
            return RiskManager()

    def test_risk_manager_global_disabled(self, risk_manager):
        """Cover lines 42-43 in risk_manager.py"""
        risk_manager.settings_repo.get.return_value = "false"
        assert risk_manager.check_constraints("user1") is False

    def test_risk_manager_consecutive_losses(self, risk_manager):
        """Cover lines 105-107 in risk_manager.py"""
        # cb_loss_streak = 3
        def mock_get(u, k):
            if k == "cb_loss_streak": return "3"
            if k == "cb_loss_pct": return "0.20"
            if k == "cb_holding_days": return "30"
            return "true" # for ai_trading_enabled
            
        risk_manager.settings_repo.get.side_effect = mock_get
        history = [
            {'profit': -100, 'date': '2025-01-04'},
            {'profit': -50, 'date': '2025-01-03'},
            {'profit': -20, 'date': '2025-01-02'},
            {'profit': -10, 'date': '2025-01-01'}
        ]
        assert risk_manager._is_circuit_breaker_triggered("user1", history=history) is True

    def test_risk_manager_holding_time_loss(self, risk_manager):
        """Cover lines 116-135 in risk_manager.py"""
        # cb_loss_pct = 0.1, cb_holding_days = 5
        risk_manager.settings_repo.get.side_effect = lambda u, k: "0.10" if k == "cb_loss_pct" else "5"
        
        # Position held for 10 days with 20% loss (ROI = -0.2)
        pos = MagicMock()
        pos.open_date = datetime.now() - timedelta(days=10)
        pos.market_value = 800
        pos.unrealized_pnl = -200 
        pos.symbol = "AAPL"
        
        assert risk_manager._is_circuit_breaker_triggered("user1", positions=[pos]) is True

    def test_risk_manager_sector_exposure_bypass(self, risk_manager):
        """Cover lines 146-147 in risk_manager.py"""
        risk_manager.settings_repo.get.return_value = "1.5" # > 1.0
        assert risk_manager.check_sector_exposure("user1", "TSLA", 1000, []) is True

    @patch('src.services.market_data_service.MarketDataService')
    def test_risk_manager_unknown_sector(self, mock_mds_cls, risk_manager):
        """Cover lines 155-156 in risk_manager.py"""
        risk_manager.settings_repo.get.return_value = "0.30"
        mock_mds = mock_mds_cls.return_value
        mock_mds.get_financials.return_value = {"sector": None} # This should cause _get_sector to return None
        
        assert risk_manager.check_sector_exposure("user1", "UNKNOWN", 1000, []) is True

    @patch('src.services.analytics_service.update_daily_snapshot')
    def test_analytics_service_trigger(self, mock_update):
        """Cover lines 283-284 in analytics_service.py"""
        with patch('src.services.analytics_service.SqliteSnapshotRepository'), \
             patch('src.services.analytics_service.PnLCalculator'):
            service = AnalyticsService(user_id="user1")
            service.trigger_snapshot_update()
            mock_update.assert_called_once()

    def test_pnl_calculator_realized_only(self):
        """Cover lines 220-228 in analytics_service.py"""
        mock_repo = MagicMock()
        # history: One Buy at 100, One Sell at 120 (Realized 20)
        t1 = MagicMock(ticker="AAPL", action="BUY", quantity=10, price=100.0, fees=0.0)
        t2 = MagicMock(ticker="AAPL", action="SELL", quantity=10, price=120.0, fees=0.0)
        mock_repo.get_all_by_user.return_value = [t2, t1] # Repo returns DESC
        
        calc = PnLCalculator(repository=mock_repo)
        res = calc.calculate_breakdown({}, "user1")
        
        assert "AAPL" in res['details']
        assert res['details']['AAPL']['qty'] == 0
        assert res['details']['AAPL']['realized'] == 200.0
