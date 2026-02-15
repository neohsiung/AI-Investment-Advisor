"""
Tests for Analytics Service (Aligned with v3.6 Implementation).
測試分析服務 (與 v3.6 實作一致).
"""
import pytest
from unittest.mock import MagicMock, patch
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
    def analytics_service(self, mock_snapshot_repo, mock_pnl_calculator):
        service = AnalyticsService(user_id="user_123", repository=mock_snapshot_repo)
        service.pnl_calculator = mock_pnl_calculator
        return service

    def test_get_performance_history(self, analytics_service, mock_snapshot_repo):
        """Test retrieving performance history."""
        mock_snapshot_repo.get_history_by_user.return_value = [{"date": "2023-01-01", "nlv": 10000}]
        
        result = analytics_service.get_performance_history()
        
        assert len(result) == 1
        assert result[0]["nlv"] == 10000
        mock_snapshot_repo.get_history_by_user.assert_called_once_with("user_123")

    def test_get_latest_performance(self, analytics_service, mock_snapshot_repo):
        """Test retrieving latest performance."""
        mock_snapshot_repo.get_latest_by_user.return_value = {"date": "2023-01-01", "nlv": 10000}
        
        result = analytics_service.get_latest_performance()
        
        assert result["nlv"] == 10000
        mock_snapshot_repo.get_latest_by_user.assert_called_once_with("user_123")

    def test_get_pnl_breakdown(self, analytics_service, mock_pnl_calculator):
        """Test converting pnl breakdown request."""
        current_prices = {"AAPL": 150}
        mock_pnl_calculator.calculate_breakdown.return_value = {"total": 500}
        
        result = analytics_service.get_pnl_breakdown(current_prices)
        
        assert result["total"] == 500
        mock_pnl_calculator.calculate_breakdown.assert_called_once_with(current_prices, "user_123")

    def test_trigger_snapshot_update(self, analytics_service):
        """Test manual trigger of snapshot update."""
        with patch('src.services.analytics_service.update_daily_snapshot') as mock_update:
            analytics_service.trigger_snapshot_update()
            mock_update.assert_called_once_with(analytics_service.db_path, "user_123")

    def test_missing_user_handling(self, mock_snapshot_repo):
        """Test service behavior when user_id is not provided."""
        service = AnalyticsService(repository=mock_snapshot_repo) # No user_id
        
        assert service.get_performance_history() is None
        assert service.get_latest_performance() is None
        assert service.get_pnl_breakdown({}) is None
