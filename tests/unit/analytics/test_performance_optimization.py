import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.analytics_service import update_daily_snapshot

@pytest.mark.asyncio
async def test_update_daily_snapshot_uses_provided_prices():
    """
    Verify that update_daily_snapshot does not call MarketDataService
    if current_prices are provided.
    """
    user_id = "test_user"
    db_path = ":memory:"
    current_prices = {"AAPL": 150.0, "MSFT": 300.0}

    # Mock dependencies
    with patch("src.services.analytics_service.AlchemySnapshotRepository") as mock_snap_repo_cls, \
         patch("src.services.analytics_service.AlchemyTransactionRepository") as mock_trans_repo_cls, \
         patch("src.services.analytics_service.MarketDataService") as mock_market_svc_cls, \
         patch("src.services.analytics_service.LeverageCalculator") as mock_calc_cls, \
         patch("src.services.analytics_service.SnapshotRecorder") as mock_recorder_cls:
        
        # Setup mocks
        mock_snap_repo = mock_snap_repo_cls.return_value
        mock_snap_repo.get_latest_by_user.return_value = None # Force update
        
        mock_trans_repo = mock_trans_repo_cls.return_value
        mock_trans_repo.get_active_tickers.return_value = ["AAPL", "MSFT"]
        
        mock_calc = mock_calc_cls.return_value
        mock_calc.calculate_metrics.return_value = {"nlv": 1000, "cash_balance": 500}
        
        # EXECUTE with provided prices — update_daily_snapshot is async
        await update_daily_snapshot(db_path=db_path, user_id=user_id, current_prices=current_prices)
        
        # VERIFY
        # MarketDataService should NOT be instantiated or called for current prices
        mock_market_svc_cls.assert_not_called()
        
        # LeverageCalculator should use our provided prices
        mock_calc.calculate_metrics.assert_called_with(current_prices, user_id)

@pytest.mark.asyncio
async def test_update_daily_snapshot_fetches_prices_if_none_provided():
    """
    Verify that update_daily_snapshot calls MarketDataService
    if current_prices is NOT provided.
    """
    user_id = "test_user"
    db_path = ":memory:"
    fetched_prices = {"TSLA": 200.0}

    # Mock dependencies
    with patch("src.services.analytics_service.AlchemySnapshotRepository") as mock_snap_repo_cls, \
         patch("src.services.analytics_service.AlchemyTransactionRepository") as mock_trans_repo_cls, \
         patch("src.services.analytics_service.MarketDataService") as mock_market_svc_cls, \
         patch("src.services.analytics_service.LeverageCalculator") as mock_calc_cls, \
         patch("src.services.analytics_service.SnapshotRecorder") as mock_recorder_cls:
        
        # Setup mocks
        mock_snap_repo = mock_snap_repo_cls.return_value
        mock_snap_repo.get_latest_by_user.return_value = None # Force update
        
        mock_trans_repo = mock_trans_repo_cls.return_value
        mock_trans_repo.get_active_tickers.return_value = ["TSLA"]
        
        mock_market_svc = mock_market_svc_cls.return_value
        # get_current_prices is async
        mock_market_svc.get_current_prices = AsyncMock(return_value=fetched_prices)
        
        mock_calc = mock_calc_cls.return_value
        mock_calc.calculate_metrics.return_value = {"nlv": 1000, "cash_balance": 500}
        
        # EXECUTE without providing prices — update_daily_snapshot is async
        await update_daily_snapshot(db_path=db_path, user_id=user_id, current_prices=None)
        
        # VERIFY
        # MarketDataService SHOULD be called
        mock_market_svc.get_current_prices.assert_called_once()
        
        # LeverageCalculator should use the fetched prices
        mock_calc.calculate_metrics.assert_called_with(fetched_prices, user_id)
