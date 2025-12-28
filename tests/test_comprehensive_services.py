"""
Comprehensive test coverage for Dashboard and Analytics Services (Fixed Imports)
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime
import sys

# Mock streamlit
sys.modules["streamlit"] = MagicMock()
sys.modules["plotly.express"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()


class TestAnalyticsService:
    """Test analytics service calculations"""
    
    def test_leverage_calculator(self):
        """Test leverage calculation logic"""
        from src.services.analytics_service import LeverageCalculator
        
        calc = LeverageCalculator()
        
        # Mock data
        prices = {'AAPL': 100}
        
        # Mock Repository
        mock_repo = Mock()
        # get_holdings_summary returns list of (ticker, quantity) tuples
        mock_repo.get_holdings_summary.return_value = [('AAPL', 12)]
        # Also called by calculate_metrics for cash calculation
        mock_repo.get_all_by_user.return_value = []
        mock_repo.get_cash_flow_sum.return_value = 10000 
        
        calc.repo = mock_repo
        
        result = calc.calculate_metrics(prices, user_id="test_user")
        
        assert 'leverage_ratio' in result
    
    def test_roi_engine(self):
        """Test ROI calculation"""
        from src.services.analytics_service import ROIEngine
        
        engine = ROIEngine()
        
        # Since it calculates based on invested capital from repo, mock repo
        mock_repo = Mock()
        # calculate_net_invested_capital returns a float
        mock_repo.calculate_net_invested_capital.return_value = 10000.0
        engine.repo = mock_repo
        
        result = engine.calculate_roi(nlv=10500, user_id="test_user")
        assert result == 5.0  # (10500 - 10000) / 10000 * 100
    
    def test_pnl_calculator_breakdown(self):
        """Test PnL breakdown calculation"""
        from src.services.analytics_service import PnLCalculator
        from types import SimpleNamespace
        
        mock_repo = Mock()
        # get_all_by_user returns iterable of rows (objects acting like rows)
        mock_repo.get_all_by_user.return_value = [
            SimpleNamespace(action='BUY', ticker='AAPL', quantity=10, price=100, fees=0, date='2023-01-01', id='1'),
            SimpleNamespace(action='SELL', ticker='AAPL', quantity=10, price=110, fees=0, date='2023-01-02', id='2')
        ]
        
        calc = PnLCalculator(repository=mock_repo)
        
        prices = {'AAPL': 110}
        
        result = calc.calculate_breakdown(prices, user_id="test_user")
        
        assert 'total' in result


class TestCacheUtility:
    """Test caching utility (ResponseCache class)"""
    
    def test_response_cache(self):
        """Test cache operations"""
        from src.utils.cache import ResponseCache
        
        # Mock DB connection and OS
        with patch('src.utils.cache.get_db_connection') as mock_conn, \
             patch('os.makedirs'):  # Mock makedirs to prevent FileNotFoundError
            
            # Setup mock DB cursor
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.execute.return_value = mock_cursor
            
            cache = ResponseCache(db_path=":memory:")
            
            # Test key generation
            key = cache._generate_key("Agent", "Prompt")
            assert isinstance(key, str)
            
            # Test get (miss)
            result = cache.get("Agent", "Prompt")
            assert result is None
            
            # Test set
            cache.set("Agent", "Prompt", "Response")
            mock_conn.return_value.execute.assert_called()


class TestSnapshotAndPerformance:
    """Test snapshot and performance calculations"""
    
    def test_performance_service(self):
        """Test performance service metrics"""
        from src.services.performance_service import PerformanceService
        
        service = PerformanceService()
        
        # Test record_recommendation
        with patch('src.services.performance_service.get_db_connection') as mock_conn:
            service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)
            mock_conn.assert_called()
    
    def test_performance_alpha(self):
        from src.services.performance_service import PerformanceService
        service = PerformanceService()
        alpha = service.calculate_portfolio_alpha(0.10, 0.08)
        # Handle floating point precision if needed, but 0.10 - 0.08 should be approx 0.02
        assert abs(alpha - 0.02) < 0.0001


class TestTransactionService:
    """Test transaction service"""
    
    def test_get_transactions(self):
        """Test fetching transactions"""
        from src.services.transaction_service import TransactionService
        
        mock_repo = Mock()
        mock_repo.get_all_by_user_df.return_value = pd.DataFrame({
            'ticker': ['AAPL']
        })
        
        service = TransactionService(repository=mock_repo)
        result = service.get_transactions(user_id='test')
        
        assert isinstance(result, pd.DataFrame)
    
    def test_add_manual_trade(self):
        """Test adding manual trade"""
        from src.services.transaction_service import TransactionService
        
        mock_repo = Mock()
        service = TransactionService(repository=mock_repo, user_id="test_user")
        
        with patch('src.services.transaction_service.update_daily_snapshot'):
             success, msg = service.add_manual_trade('AAPL', '2023-01-01', 'BUY', 10, 150.0, 0)
             assert success is True
             mock_repo.add.assert_called()


class TestWorkflowFiles:
    """Test workflow classes"""
    
    def test_daily_workflow_init(self):
        """Test DailyWorkflow initialization"""
        from src.services.workflow_service import DailyWorkflow
        
        wf = DailyWorkflow(user_id="test")
        assert wf.user_id == "test"
    
    @patch('src.services.workflow_service.MarketDataService')
    @patch('src.services.workflow_service.AgentFactory')
    def test_daily_workflow_execution(self, mock_factory, mock_market):
        """Test DailyWorkflow execution logic (Dry Run)"""
        from src.services.workflow_service import DailyWorkflow
        
        wf = DailyWorkflow(user_id="test")
        
        # Mock dependencies
        wf.market_service = Mock()
        wf.market_service.get_yield_curve_inversion.return_value = {'inverted': False}
        
        # Run dry run
        with patch.object(wf, 'synthesize_results'):
             wf.run(dry_run=True)
             # Should run without error
