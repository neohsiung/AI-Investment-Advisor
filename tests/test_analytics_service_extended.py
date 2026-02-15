"""
Extended tests for Analytics Service - Edge Cases & Missing Coverage.
測試分析服務的邊緣情況與缺失覆蓋。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.analytics_service import AnalyticsService


class TestAnalyticsServiceExtended:
    """Extended tests for Analytics Service missing coverage areas."""
    
    @pytest.fixture
    def mock_portfolio_repo(self):
        """Mock portfolio repository."""
        repo = MagicMock()
        repo.get_all_positions.return_value = []
        return repo
    
    @pytest.fixture
    def mock_transaction_repo(self):
        """Mock transaction repository."""
        repo = MagicMock()
        repo.get_all.return_value = []
        return repo
    
    @pytest.fixture
    def analytics_service(self, mock_portfolio_repo, mock_transaction_repo):
        """Create analytics service with mocked repositories."""
        with patch('src.services.analytics_service.PortfolioRepository', return_value=mock_portfolio_repo):
            with patch('src.services.analytics_service.TransactionRepository', return_value=mock_transaction_repo):
                service = AnalyticsService()
                service.portfolio_repo = mock_portfolio_repo
                service.transaction_repo = mock_transaction_repo
                return service
    
    def test_calculate_portfolio_performance_empty_portfolio(self, analytics_service, mock_portfolio_repo):
        """Test portfolio performance calculation with empty portfolio."""
        mock_portfolio_repo.get_all_positions.return_value = []
        
        result = analytics_service.calculate_portfolio_performance("user_123")
        
        # Should handle empty portfolio gracefully
        assert result is not None
        assert isinstance(result, dict)
    
    def test_calculate_returns_with_no_transactions(self, analytics_service, mock_transaction_repo):
        """Test returns calculation when no transactions exist."""
        mock_transaction_repo.get_all.return_value = []
        
        result = analytics_service.calculate_returns("user_123")
        
        assert result is not None
    
    def test_get_sector_allocation_empty(self, analytics_service, mock_portfolio_repo):
        """Test sector allocation with no positions."""
        mock_portfolio_repo.get_all_positions.return_value = []
        
        allocation = analytics_service.get_sector_allocation("user_123")
        
        assert allocation == {} or len(allocation) == 0
    
    def test_calculate_sharpe_ratio_zero_volatility(self, analytics_service):
        """Test Sharpe ratio calculation with zero volatility."""
        with patch.object(analytics_service, 'calculate_returns', return_value=[]):
            sharpe = analytics_service.calculate_sharpe_ratio("user_123")
            
            # Should handle zero volatility (return 0 or None)
            assert sharpe == 0 or sharpe is None
    
    def test_calculate_max_drawdown_no_data(self, analytics_service):
        """Test max drawdown with no historical data."""
        with patch.object(analytics_service, 'get_portfolio_value_history', return_value=[]):
            drawdown = analytics_service.calculate_max_drawdown("user_123")
            
            assert drawdown == 0 or drawdown is None
    
    def test_get_performance_metrics_with_invalid_user(self, analytics_service):
        """Test performance metrics for invalid/non-existent user."""
        with patch.object(analytics_service.portfolio_repo, 'get_all_positions', return_value=[]):
            metrics = analytics_service.get_performance_metrics("nonexistent_user")
            
            assert isinstance(metrics, dict)
    
    def test_calculate_win_rate_no_closed_positions(self, analytics_service, mock_transaction_repo):
        """Test win rate calculation with no closed positions."""
        mock_transaction_repo.get_all.return_value = []
        
        win_rate = analytics_service.calculate_win_rate("user_123")
        
        assert win_rate == 0 or win_rate is None
    
    def test_get_top_performers_empty_portfolio(self, analytics_service, mock_portfolio_repo):
        """Test getting top performers from empty portfolio."""
        mock_portfolio_repo.get_all_positions.return_value = []
        
        top = analytics_service.get_top_performers("user_123", limit=5)
        
        assert top == []
    
    def test_get_worst_performers_empty_portfolio(self, analytics_service, mock_portfolio_repo):
        """Test getting worst performers from empty portfolio."""
        mock_portfolio_repo.get_all_positions.return_value = []
        
        worst = analytics_service.get_worst_performers("user_123", limit=5)
        
        assert worst == []
