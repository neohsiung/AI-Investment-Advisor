import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta
from src.infrastructure.risk_manager import RiskManager

@pytest.fixture
def risk_manager():
    with patch('src.infrastructure.risk_manager.AlchemyTransactionRepository'), \
         patch('src.infrastructure.risk_manager.AlchemySettingsRepository'):
        rm = RiskManager()
        rm.transaction_repo = MagicMock()
        rm.settings_repo = MagicMock()
        return rm

def test_get_dynamic_thresholds_empty(risk_manager):
    # Setup: Empty transaction history
    risk_manager.transaction_repo.get_all_by_user_df.return_value = pd.DataFrame()
    
    thresholds = risk_manager._get_dynamic_thresholds("user_123")
    
    assert thresholds["max_daily_trades"] == 3
    assert thresholds["loss_pct_threshold"] == 0.10

def test_get_dynamic_thresholds_with_data(risk_manager):
    # Setup: Some trades in last 30 days
    today = datetime.now().date()
    data = {
        'trade_date': [today, today, today - timedelta(days=1)],
        'action': ['BUY', 'BUY', 'BUY'],
        'ticker': ['AAPL', 'MSFT', 'TSLA']
    }
    risk_manager.transaction_repo.get_all_by_user_df.return_value = pd.DataFrame(data)
    
    thresholds = risk_manager._get_dynamic_thresholds("user_123")
    
    # Avg trades per day: (2 + 1) / 2 = 1.5
    # Since std is small, max_daily should be at least 3
    assert thresholds["max_daily_trades"] >= 3
    assert thresholds["loss_pct_threshold"] == 0.15

def test_check_constraints_disabled(risk_manager):
    risk_manager.settings_repo.get.return_value = "false"
    
    allowed = risk_manager.check_constraints("user_123")
    
    assert allowed is False
    risk_manager.settings_repo.get.assert_any_call("user_123", "ai_trading_enabled")

def test_check_constraints_daily_limit_reached(risk_manager):
    risk_manager.settings_repo.get.side_effect = lambda u, k: "true" if k == "ai_trading_enabled" else "2"
    risk_manager.transaction_repo.get_all_by_user.return_value = [
        MagicMock(trade_date=datetime.now().date()),
        MagicMock(trade_date=datetime.now().date())
    ]
    
    # thresholds will return max_daily_trades=3 by default if no data
    risk_manager.transaction_repo.get_all_by_user_df.return_value = pd.DataFrame()

    allowed = risk_manager.check_constraints("user_123")
    
    assert allowed is False

def test_circuit_breaker_streak(risk_manager):
    # Setup: 3 consecutive losses
    history = [
        {'date': '2026-04-05', 'profit': -100},
        {'date': '2026-04-04', 'profit': -50},
        {'date': '2026-04-03', 'profit': -20}
    ]
    risk_manager.settings_repo.get.side_effect = lambda u, k: "3" if k == "cb_loss_streak" else None
    
    triggered = risk_manager._is_circuit_breaker_triggered("user_123", history=history)
    
    assert triggered is True

def test_sector_exposure_limit(risk_manager):
    # Setup: 30% sector limit
    risk_manager.settings_repo.get.return_value = "0.30"
    
    with patch('src.services.market_data_service.MarketDataService') as mock_mds:
        # Mock sector for existing position and new trade
        mock_instance = mock_mds.return_value
        mock_instance.get_financials.return_value = {'sector': 'Technology'}
        
        current_positions = [
            MagicMock(symbol='AAPL', market_value=200)
        ]
        
        # New trade: 100 in Tech. Total Tech = 300. Total Portfolio = 300. Exposure = 100%
        allowed = risk_manager.check_sector_exposure("user_123", "MSFT", 100, current_positions)
        
        assert allowed is False

def test_kill_switch(risk_manager):
    risk_manager.trigger_kill_switch("user_123")
    risk_manager.settings_repo.set.assert_called_with("user_123", "ai_trading_enabled", "false")
