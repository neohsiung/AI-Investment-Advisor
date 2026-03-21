"""
Comprehensive test coverage for Dashboard and Analytics Services (Fixed Imports)
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime
import sys

# Mock problematic modules (Streamlit is centrally mocked in conftest.py)
sys.modules["plotly.express"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()


class TestAnalyticsService:
    """Test analytics service calculations"""
    
    def test_leverage_calculator(self):
        """Test leverage calculation logic"""
        from src.services.analytics_service import LeverageCalculator
        
        calc = LeverageCalculator(user_id="test_user")
        
        # Mock data
        prices = {'AAPL': 100}
        
        # Mock Repository
        mock_repo = Mock()
        # get_leverage_summary returns list of (ticker, quantity, leverage) tuples
        mock_repo.get_leverage_summary.return_value = [('AAPL', 12, 1.0)]
        # get_cash_balance returns total cash
        mock_repo.get_cash_balance.return_value = 10000
    
        calc.repo = mock_repo
    
        result = calc.calculate_metrics(prices, user_id="test_user")
        
        # NLV = 10000 (cash) + 1200 (equity) = 11200
        # TNV = 12 * 100 * 1.0 = 1200
        # Ratio = 1200 / 11200 = 0.10714...
        assert result['leverage_ratio'] == pytest.approx(0.10714, rel=1e-3)
        assert result['tnv'] == 1200.0
        
    def test_roi_engine(self):
        """Test ROI calculation"""
        from src.services.analytics_service import ROIEngine
        
        engine = ROIEngine(user_id="test_user")
        
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
        
        calc = PnLCalculator(user_id="test_user", repository=mock_repo)
        
        prices = {'AAPL': 110}
        
        result = calc.calculate_breakdown(prices, user_id="test_user")
        
        assert 'total' in result


class TestCacheUtility:
    """Test caching utility (ResponseCache class)"""
    
    def test_response_cache(self):
        """Test cache operations"""
        from src.utils.cache import ResponseCache
        
        # Mock redis.from_url
        with patch('redis.from_url') as mock_redis_factory:
            mock_client = MagicMock()
            mock_redis_factory.return_value = mock_client
            
            cache = ResponseCache(redis_url="redis://localhost:6379/0")
            
            # Test key generation
            key = cache._generate_key("Agent", "Prompt")
            assert "cache:response:Agent" in key
            
            # Test get (miss)
            mock_client.get.return_value = None
            result = cache.get("Agent", "Prompt")
            assert result is None
            
            # Test set
            cache.set("Agent", "Prompt", "Response")
            mock_client.setex.assert_called_once()


class TestSnapshotAndPerformance:
    """Test snapshot and performance calculations"""
    
    def test_performance_service(self):
        """Test performance service metrics"""
        from src.services.performance_service import PerformanceService
        
        service = PerformanceService(user_id="test_user")
        
        # Test record_recommendation
        with patch('src.data.database.get_db_engine') as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__.return_value = mock_conn
            service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)
            mock_conn.execute.assert_called()
    
    def test_performance_alpha(self):
        from src.services.performance_service import PerformanceService
        service = PerformanceService(user_id="test_user")
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
    @pytest.mark.asyncio
    async def test_daily_workflow_execution(self, mock_factory, mock_market):
        """Test DailyWorkflow execution logic (Dry Run)"""
        from src.services.workflow_service import DailyWorkflow
        
        # Mock AlchemyTransactionRepository WHERE IT IS USED
        # DailyWorkflow is in src.services.workflow_service
        # It imports AlchemyTransactionRepository.
        # So we must patch src.services.workflow_service.AlchemyTransactionRepository
        with patch('src.services.workflow_service.AlchemyTransactionRepository') as MockRepo:
             MockRepo.return_value.get_active_tickers.return_value = ['AAPL']
             
             # Instantiate INSIDE the patch so it uses the mock
             wf = DailyWorkflow(user_id="test")

             # Mock dependencies on the instance (if not passed in init or set later)
             wf.market_service = Mock()
             wf.market_service.get_yield_curve_inversion.return_value = {'inverted': False}
             wf.context['tickers'] = ['AAPL'] # Ensure we have tickers to avoid early return

             # Run dry run
             # synthesize_results creates Agents which create NEW Repos. 
             # We should patch synthesize_results to avoid that.
             with patch.object(wf, 'synthesize_results'):
                  # Also avoid PerformanceService DB hits in execute_analysis
                  wf.performance_service = Mock()
                  
                  # Avoid AgentFactory creating agents that hit DB?
                  # execute_analysis creates Mom/Sent agents using Factory.
                  # These agents might use DB?
                  # MomentumAgent uses market data.
                  # Check if we need to mock Factory.
                  # For now, let's assume Agents don't hit Transaction DB directly in run()
                  # But wait, logic earlier said they do?
                  # "Record Recommendations for Performance Tracking" -> uses wf.performance_service.
                  # We mocked wf.performance_service.
                  
                  await wf.run(dry_run=True)
