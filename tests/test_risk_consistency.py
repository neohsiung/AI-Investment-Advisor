import pytest
from unittest.mock import MagicMock, patch
from src.services.sentinel_service import SentinelService
from datetime import date

@pytest.mark.asyncio
async def test_check_risk_consistency_balanced_high_leverage():
    # Mock services
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda uid, key, default: "Balanced" if key == "risk_profile" else default
    
    mock_snapshot_repo = MagicMock()
    # Mock latest snapshot with 1.8x leverage
    mock_snapshot_repo.get_latest_by_user.return_value = {
        "leverage_ratio": 1.8,
        "total_nlv": 100000,
        "cash_balance": 20000
    }
    
    with patch("src.services.sentinel_service.SettingsService", return_value=mock_settings), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository", return_value=mock_snapshot_repo), \
         patch("src.services.sentinel_service.AlchemySentinelRepository") as mock_sentinel_repo_class, \
         patch("src.services.fred_service.FredService") as mock_fred_class, \
         patch("src.services.sentinel_service.InternetSearchService"), \
         patch("src.services.sentinel_service.TransactionService"), \
         patch("src.services.sentinel_service.CouncilService"):
        
        # Mock Sentinel Repo to avoid DB hits in constructor
        mock_sentinel_repo = MagicMock()
        mock_sentinel_repo.engine = MagicMock()
        mock_sentinel_repo.get_all_thresholds.return_value = {}
        mock_sentinel_repo_class.return_value = mock_sentinel_repo

        # Mock FredService indicators
        mock_fred = MagicMock()
        mock_fred.get_macro_indicators.return_value = {"CPI": {"history": [110, 100]}}
        mock_fred_class.return_value = mock_fred
        
        service = SentinelService(
            settings_service=mock_settings,
            repo=mock_sentinel_repo,
            snapshot_repo=mock_snapshot_repo
        )
        service._get_all_user_ids = MagicMock(return_value=["test_user"])
        
        triggers = await service._check_risk_consistency()
        
        # Assertions
        risk_trigger = next((t for t in triggers if t["type"] == "risk_consistency"), None)
        assert risk_trigger is not None
        assert "Risk Mapping Alert" in risk_trigger["text"]
        assert "1.80x" in risk_trigger["text"]

@pytest.mark.asyncio
async def test_check_cash_ratio_low_alarm():
    mock_settings = MagicMock()
    # Target cash 20%
    mock_settings.get_setting.side_effect = lambda uid, key, default: 0.2 if key == "target_cash_ratio" else "Aggressive" if key == "risk_profile" else default
    
    mock_snapshot_repo = MagicMock()
    # Actual cash 5% (5000 / 100000)
    mock_snapshot_repo.get_latest_by_user.return_value = {
        "leverage_ratio": 1.0,
        "total_nlv": 100000,
        "cash_balance": 5000
    }
    
    with patch("src.services.sentinel_service.SettingsService", return_value=mock_settings), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository", return_value=mock_snapshot_repo), \
         patch("src.services.sentinel_service.AlchemySentinelRepository") as mock_sentinel_repo_class, \
         patch("src.services.fred_service.FredService") as mock_fred_class, \
         patch("src.services.sentinel_service.InternetSearchService"), \
         patch("src.services.sentinel_service.TransactionService"), \
         patch("src.services.sentinel_service.CouncilService"):
        
        mock_sentinel_repo = MagicMock()
        mock_sentinel_repo.engine = MagicMock()
        mock_sentinel_repo.get_all_thresholds.return_value = {}
        mock_sentinel_repo_class.return_value = mock_sentinel_repo

        mock_fred = MagicMock()
        mock_fred.get_macro_indicators.return_value = {"CPI": {"history": [100, 100]}} # Zero inflation
        mock_fred_class.return_value = mock_fred
        
        service = SentinelService(
            settings_service=mock_settings,
            repo=mock_sentinel_repo,
            snapshot_repo=mock_snapshot_repo
        )
        service._get_all_user_ids = MagicMock(return_value=["test_user"])
        service._check_vix_anomaly = MagicMock(return_value=[]) # Normal VIX
        
        triggers = await service._check_risk_consistency()
        
        cash_trigger = next((t for t in triggers if t["type"] == "cash_management"), None)
        assert cash_trigger is not None
        assert "Cash Alert" in cash_trigger["text"]
        assert "Actual 5.0%" in cash_trigger["text"]
