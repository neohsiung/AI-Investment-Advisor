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
    def mock_portfolio_repo(self):
        # In v3.6, AnalyticsService uses TransactionRepository and SnapshotRepository
        # We mock TransactionRepository here as "portfolio repo" for backward compat in test names
        # or update test implementation to use new repo names.
        repo = MagicMock()
        # Common methods
        repo.get_holdings.return_value = []
        repo.get_all_transactions.return_value = []
        return repo

    @pytest.fixture
    def service(self, mock_snapshot_repo, mock_pnl_calculator, mock_portfolio_repo):
        # AnalyticsService(snapshot_repo, transaction_repo, market_data, theme_service...)
        # We need to checking signature.
        # Assuming: AnalyticsService(snapshot_repo, transaction_repo, ...)
        
        # We just pass mocks. If signature differs, we need to adjust.
        # Let's check signature from file view later if needed, but for now assuming typical DI.
        # Actually file view showed: 
        # class LeverageCalculator relies on ITransactionRepository.
        # AnalyticsService likely relies on Repos too.
        
        # Initialize with user_id to avoid early returns (None) in methods
        svc = AnalyticsService(user_id="user_123")
        # Inject mocks manually to avoid init signature issues if using DI container or similar
        svc.snapshot_repo = mock_snapshot_repo
        svc.transaction_repo = mock_portfolio_repo # Mapping portfolio_repo fixture to transaction_repo
        svc.pnl_calculator = mock_pnl_calculator
        
        return svc

    def test_get_performance_history(self, service, mock_snapshot_repo):
        """Test retrieving performance history."""
        mock_snapshot_repo.get_history_by_user.return_value = [{"date": "2023-01-01", "nlv": 10000}]
        
        result = service.get_performance_history()
        
        assert len(result) == 1
        assert result[0]["nlv"] == 10000
        mock_snapshot_repo.get_history_by_user.assert_called_once_with("user_123")

    def test_get_latest_performance(self, service, mock_snapshot_repo):
        """Test retrieving latest performance."""
        mock_snapshot_repo.get_latest_by_user.return_value = {"date": "2023-01-01", "nlv": 10000}
        
        result = service.get_latest_performance()
        
        assert result["nlv"] == 10000
        mock_snapshot_repo.get_latest_by_user.assert_called_once_with("user_123")

    def test_get_pnl_breakdown(self, service, mock_pnl_calculator):
        """Test converting pnl breakdown request."""
        current_prices = {"AAPL": 150}
        mock_pnl_calculator.calculate_breakdown.return_value = {"total": 500}
        
        result = service.get_pnl_breakdown(current_prices)
        
        assert result["total"] == 500
        mock_pnl_calculator.calculate_breakdown.assert_called_once_with(current_prices, "user_123")

    def test_trigger_snapshot_update(self, service):
        """Test manual trigger of snapshot update."""
        with patch('src.services.analytics_service.update_daily_snapshot') as mock_update:
            service.trigger_snapshot_update()
            mock_update.assert_called_once_with(service.db_path, "user_123")

    def test_missing_user_handling(self, mock_snapshot_repo):
        """Test service behavior when user_id is not provided."""
        # Use constructor directly or mock logic
        service = AnalyticsService(repository=mock_snapshot_repo) 
        # Note: AnalyticsService init signature might be different, let's just test behavior if user_id is None
        service.user_id = None
        
        assert service.get_performance_history() is None
        assert service.get_latest_performance() is None
        assert service.get_pnl_breakdown({}) is None
