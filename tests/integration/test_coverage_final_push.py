
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from src.infrastructure.risk_manager import RiskManager
from src.services.analytics_service import AnalyticsService, PnLCalculator

class TestCoverageFinalPush:
    
    @pytest.fixture
    def risk_manager(self):
        with patch('src.infrastructure.risk_manager.AlchemyTransactionRepository'), \
             patch('src.infrastructure.risk_manager.AlchemySettingsRepository'):
            rm = RiskManager()
            # Fulfill Rule #8: ensure dynamic thresholds can be computed if needed
            rm.transaction_repo.get_all_by_user_df.return_value = MagicMock() 
            return rm

    def test_risk_manager_global_disabled(self, risk_manager):
        """Cover global enabled check."""
        risk_manager.settings_repo.get.return_value = "false"
        assert risk_manager.check_constraints("user1") is False

    def test_risk_manager_consecutive_losses(self, risk_manager):
        """Cover loss analysis streak."""
        thresholds = {
            "max_daily_trades": 5,
            "loss_streak_limit": 3,
            "holding_days_limit": 30,
            "loss_pct_threshold": 0.20
        }
        
        # Mock settings to return None so it uses thresholds
        risk_manager.settings_repo.get.return_value = None
        
        history = [
            {'profit': -100, 'date': '2025-01-04'},
            {'profit': -50, 'date': '2025-01-03'},
            {'profit': -20, 'date': '2025-01-02'},
            {'profit': -10, 'date': '2025-01-01'}
        ]
        assert risk_manager._is_circuit_breaker_triggered("user1", history=history, thresholds=thresholds) is True

    def test_risk_manager_holding_time_loss(self, risk_manager):
        """Cover holding time analysis."""
        thresholds = {
            "max_daily_trades": 5,
            "loss_streak_limit": 3,
            "holding_days_limit": 5,
            "loss_pct_threshold": 0.10
        }
        
        risk_manager.settings_repo.get.return_value = None
        
        # Position held for 10 days with 20% loss (ROI = -0.2)
        pos = MagicMock()
        # Ensure year exists for hasattr check
        pos.open_date = datetime.now() - timedelta(days=10)
        pos.market_value = 800
        pos.unrealized_pnl = -200 
        pos.symbol = "AAPL"
        
        assert risk_manager._is_circuit_breaker_triggered("user1", positions=[pos], thresholds=thresholds) is True

    def test_risk_manager_sector_exposure_bypass(self, risk_manager):
        """Cover sector exposure bypass."""
        risk_manager.settings_repo.get.return_value = "1.5" # > 1.0
        assert risk_manager.check_sector_exposure("user1", "TSLA", 1000, []) is True

    @patch('src.services.market_data_service.MarketDataService')
    def test_risk_manager_unknown_sector(self, mock_mds_cls, risk_manager):
        """Cover unknown sector case."""
        risk_manager.settings_repo.get.return_value = "0.30"
        mock_mds = mock_mds_cls.return_value
        mock_mds.get_financials.return_value = {"sector": None} 
        
        assert risk_manager.check_sector_exposure("user1", "UNKNOWN", 1000, []) is True

    @patch('src.services.analytics_service.update_daily_snapshot')
    @pytest.mark.asyncio
    async def test_analytics_service_trigger(self, mock_update):
        """Cover analytics service trigger."""
        with patch('src.services.analytics_service.AlchemySnapshotRepository'), \
             patch('src.services.analytics_service.PnLCalculator'):
            service = AnalyticsService(user_id="user1")
            await service.trigger_snapshot_update()
            mock_update.assert_called_once()

    def test_pnl_calculator_realized_only(self):
        """Cover PnL calculator breakdown."""
        mock_repo = MagicMock()
        # history: One Buy at 100, One Sell at 120 (Realized 20)
        t1 = MagicMock(ticker="AAPL", action="BUY", quantity=10, price=100.0, fees=0.0)
        t2 = MagicMock(ticker="AAPL", action="SELL", quantity=10, price=120.0, fees=0.0)
        mock_repo.get_all_by_user.return_value = [t2, t1] 
        
        calc = PnLCalculator(user_id="user1", repository=mock_repo)
        res = calc.calculate_breakdown({}, "user1")
        
        assert "AAPL" in res['details']
        assert res['details']['AAPL']['qty'] == 0
        assert res['details']['AAPL']['realized'] == 200.0
