import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from src.services.dashboard_service import DashboardService

class TestDashboardService:
    
    @pytest.fixture
    def mock_db_path(self, tmp_path):
        """Create a temporary database path"""
        return str(tmp_path / "test_portfolio.db")
    
    @pytest.fixture
    def service(self, mock_db_path):
        """Create a DashboardService instance"""
        with patch('src.services.dashboard_service.SqliteTransactionRepository'):
            with patch('src.services.dashboard_service.TransactionService'):
                with patch('src.services.dashboard_service.MarketDataService'):
                    with patch('src.services.dashboard_service.LeverageCalculator'):
                        with patch('src.services.dashboard_service.ROIEngine'):
                            with patch('src.services.dashboard_service.PnLCalculator'):
                                with patch('src.services.portfolio_aggregator_service.PortfolioAggregatorService') as mock_agg_cls:
                                    mock_agg_cls.return_value.get_aggregated_portfolio.return_value = {'total_equity': 0, 'positions': []}
                                    yield DashboardService(db_path=mock_db_path)
    
    def test_init(self, service, mock_db_path):
        """Test service initialization"""
        assert service.db_path == mock_db_path
        assert service.transaction_repo is not None
        assert service.transaction_service is not None
        assert service.market_service is not None
        assert service.calc is not None
        assert service.roi_engine is not None
        assert service.pnl_calc is not None
    
    @patch('src.services.dashboard_service.update_daily_snapshot')
    def test_prepare_dashboard_data_empty_transactions(self, mock_update, service):
        """Test prepare_dashboard_data with no transactions"""
        # Mock empty transactions
        service.transaction_service.get_transactions = Mock(return_value=pd.DataFrame())
        # Mock market prices to bypass st.cache_data
        service._fetch_market_prices = Mock(return_value={})
        
        result = service.prepare_dashboard_data("test@example.com")
        
        assert 'transactions_df' in result
        assert 'current_prices' in result
        assert 'metrics' in result
        assert 'pnl_data' in result
        assert 'roi' in result
        assert 'positions_df' in result
        
        assert result['transactions_df'].empty
        assert result['current_prices'] == {}
        assert result['positions_df'].empty
    
    @patch('src.services.dashboard_service.update_daily_snapshot')
    def test_prepare_dashboard_data_with_transactions(self, mock_update, service):
        """Test prepare_dashboard_data with actual transactions"""
        # Mock transactions
        transactions_df = pd.DataFrame({
            'ticker': ['AAPL', 'AAPL', 'GOOGL'],
            'action': ['BUY', 'BUY', 'BUY'],
            'quantity': [10, 5, 20],
            'price': [150, 155, 2800]
        })
        service.transaction_service.get_transactions = Mock(return_value=transactions_df)
        
        # Mock market prices
        service._fetch_market_prices = Mock(return_value={'AAPL': 160, 'GOOGL': 2900})
        
        # Mock calculators
        service.calc.calculate_metrics = Mock(return_value={
            'nlv': 100000,
            'cash_balance': 50000,
            'leverage_ratio': 1.2
        })
        service.pnl_calc.calculate_breakdown = Mock(return_value={
            'unrealized': 1000,
            'realized': 500,
            'total': 1500
        })
        service.roi_engine.calculate_roi = Mock(return_value=15.5)
        
        result = service.prepare_dashboard_data("test@example.com")
        
        assert not result['transactions_df'].empty
        assert len(result['current_prices']) == 2
        assert result['metrics']['nlv'] == 100000
        assert result['pnl_data']['total'] == 1500
        assert result['roi'] == 15.5
        assert not result['positions_df'].empty
    
    @patch('src.services.dashboard_service.update_daily_snapshot')
    def test_prepare_dashboard_data_calculation_error(self, mock_update, service):
        """Test prepare_dashboard_data handles calculation errors gracefully"""
        # Mock transactions
        transactions_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'action': ['BUY'],
            'quantity': [10],
            'price': [150]
        })
        service.transaction_service.get_transactions = Mock(return_value=transactions_df)
        service._fetch_market_prices = Mock(return_value={'AAPL': 160})
        
        # Mock calculator to raise exception
        service.calc.calculate_metrics = Mock(side_effect=Exception("Calculation error"))
        
        result = service.prepare_dashboard_data("test@example.com")
        
        # Should return default values
        assert result['metrics']['nlv'] == 0
        assert result['pnl_data']['total'] == 0
        assert result['roi'] == 0
