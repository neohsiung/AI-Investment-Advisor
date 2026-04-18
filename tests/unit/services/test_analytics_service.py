"""
Tests for Analytics Service (Aligned with v9.0 Asynchronous Implementation).
測試分析服務 (與 v9.0 非同步實作一致).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.analytics_service import AnalyticsService

class TestAnalyticsService:
    @pytest.fixture
    def mock_snapshot_repo(self):
        repo = MagicMock()
        return repo

    @pytest.fixture
    def mock_pnl_calculator(self):
        calc = MagicMock()
        return calc

    @pytest.fixture
    def mock_transaction_repo(self):
        repo = MagicMock()
        # Common methods
        repo.get_leverage_summary.return_value = []
        repo.get_all_by_user.return_value = []
        repo.get_cash_balance.return_value = 0.0
        return repo

    @pytest.fixture
    def service(self, mock_snapshot_repo, mock_pnl_calculator, mock_transaction_repo):
        # AnalyticsService uses TransactionRepository and SnapshotRepository
        svc = AnalyticsService(user_id="user_123", repository=mock_snapshot_repo, pnl_calc=mock_pnl_calculator)
        svc.transaction_repo = mock_transaction_repo
        
        return svc

    def test_get_performance_history(self, service, mock_snapshot_repo):
        """Test retrieving performance history (Sync)."""
        mock_snapshot_repo.get_history_by_user.return_value = [{"date": "2023-01-01", "nlv": 10000}]
        
        result = service.get_performance_history()
        
        assert len(result) == 1
        assert result[0]["nlv"] == 10000
        mock_snapshot_repo.get_history_by_user.assert_called_once_with("user_123", None)

    def test_get_latest_performance(self, service, mock_snapshot_repo):
        """Test retrieving latest performance (Sync)."""
        mock_snapshot_repo.get_latest_by_user.return_value = {"date": "2023-01-01", "nlv": 10000}
        
        result = service.get_latest_performance()
        
        assert result["nlv"] == 10000
        mock_snapshot_repo.get_latest_by_user.assert_called_once_with("user_123", None)

    def test_get_pnl_breakdown(self, service, mock_pnl_calculator):
        """Test converting pnl breakdown request (Sync)."""
        current_prices = {"AAPL": 150}
        mock_pnl_calculator.calculate_breakdown.return_value = {"total": 500}
        
        result = service.get_pnl_breakdown(current_prices)
        
        assert result["total"] == 500
        mock_pnl_calculator.calculate_breakdown.assert_called_once_with(current_prices, "user_123", None)

    @pytest.mark.asyncio
    async def test_trigger_snapshot_update(self, service):
        """Test manual trigger of snapshot update (Async)."""
        with patch('src.services.analytics_service.update_daily_snapshot', new_callable=AsyncMock) as mock_update:
            # mock service.engine_url to avoid issues if used
            service.engine_url = "postgresql://..."
            await service.trigger_snapshot_update()
            mock_update.assert_called_once()
            args, kwargs = mock_update.call_args
            # Call is: update_daily_snapshot(self.db_path, self.user_id, force=force, current_prices=current_prices, account_id=account_id)
            assert args[1] == "user_123"

    def test_missing_user_handling(self, mock_snapshot_repo):
        """Test service behavior when user_id is not provided."""
        service = AnalyticsService(user_id=None, repository=mock_snapshot_repo)
        
        assert service.get_performance_history() is None
        assert service.get_latest_performance() is None
        assert service.get_pnl_breakdown({}) is None
