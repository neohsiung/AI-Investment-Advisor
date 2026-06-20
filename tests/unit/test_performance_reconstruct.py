"""
Unit tests for PerformanceService.reconstruct_history NaN leverage fix.
Tests that NaN/None leverage values default to 1.0 instead of causing NaN propagation.

Uses module-level mocking to avoid deep import chains (pgvector, fredapi, etc.).
"""
import sys
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Mock problematic modules before importing PerformanceService
sys.modules['fredapi'] = MagicMock()
sys.modules['src.services.fred_service'] = MagicMock()
sys.modules['src.data.providers.fred_provider'] = MagicMock()

# Now safe to import
from src.services.performance_service import PerformanceService


@pytest.fixture
def mock_deps():
    """Create mocked dependencies for PerformanceService."""
    with patch('src.services.performance_service.AlchemyTransactionRepository') as mock_repo_cls, \
         patch('src.services.performance_service.MarketDataService') as mock_mkt_cls, \
         patch('src.services.performance_service.AnalyticsService') as mock_analytics_cls:

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_mkt = MagicMock()
        mock_mkt_cls.return_value = mock_mkt

        mock_analytics = MagicMock()
        mock_analytics_cls.return_value = mock_analytics

        yield {
            'repo': mock_repo,
            'mkt': mock_mkt,
            'analytics': mock_analytics,
        }


def make_tx_df(ticker, action, qty, price, amount, trade_date, leverage=1.0, entry_category=None):
    """Helper to create a single-row transaction DataFrame."""
    return pd.DataFrame([{
        'id': 'test-id',
        'user_id': 'test-user',
        'ticker': ticker,
        'trade_date': trade_date,
        'action': action,
        'quantity': qty,
        'price': price,
        'fees': 0.0,
        'amount': amount,
        'currency': 'USD',
        'leverage': leverage,
        'source_file': None,
        'entry_category': entry_category,
        'raw_data': None,
        'created_at': None,
        'updated_at': None,
    }])


class TestReconstructHistoryNaNleverage:
    """Test that reconstruct_history handles NaN/None leverage correctly."""

    def test_nan_leverage_defaults_to_one(self, mock_deps):
        """
        Old transactions may have leverage=NULL (NaN in DataFrame).
        This should default to 1.0 instead of causing NaN in cash calculation.
        """
        tx_df = make_tx_df(
            ticker='AAPL', action='BUY', qty=10.0, price=150.0,
            amount=1500.0, trade_date='2026-06-01',
            leverage=float('nan')
        )

        mock_deps['repo'].get_all_by_user_df.return_value = tx_df
        mock_deps['mkt'].get_ohlcv_batch.return_value = {}

        service = PerformanceService(user_id='test-user')
        result = service.reconstruct_history('test-user')

        assert not result.empty, "Result should not be empty despite NaN leverage"
        last_row = result.iloc[-1]
        assert last_row['cash_balance'] == -1500.0, \
            f"Expected cash=-1500.0, got {last_row['cash_balance']}"
        assert last_row['total_nlv'] == 0.0, \
            f"Expected nlv=0.0, got {last_row['total_nlv']}"

    def test_none_leverage_defaults_to_one(self, mock_deps):
        """None leverage (from DB NULL) should also default to 1.0."""
        tx_df = make_tx_df(
            ticker='AAPL', action='BUY', qty=10.0, price=150.0,
            amount=1500.0, trade_date='2026-06-01',
            leverage=None
        )

        mock_deps['repo'].get_all_by_user_df.return_value = tx_df
        mock_deps['mkt'].get_ohlcv_batch.return_value = {}

        service = PerformanceService(user_id='test-user')
        result = service.reconstruct_history('test-user')

        assert not result.empty
        last_row = result.iloc[-1]
        assert last_row['cash_balance'] == -1500.0

    def test_zero_leverage_defaults_to_one(self, mock_deps):
        """Zero leverage (edge case) should default to 1.0 to avoid division by zero."""
        tx_df = make_tx_df(
            ticker='AAPL', action='BUY', qty=10.0, price=150.0,
            amount=1500.0, trade_date='2026-06-01',
            leverage=0.0
        )

        mock_deps['repo'].get_all_by_user_df.return_value = tx_df
        mock_deps['mkt'].get_ohlcv_batch.return_value = {}

        service = PerformanceService(user_id='test-user')
        result = service.reconstruct_history('test-user')

        assert not result.empty
        last_row = result.iloc[-1]
        assert last_row['cash_balance'] == -1500.0

    def test_normal_leverage_still_works(self, mock_deps):
        """Normal leverage values should still work correctly."""
        tx_df = make_tx_df(
            ticker='AAPL', action='BUY', qty=10.0, price=150.0,
            amount=1500.0, trade_date='2026-06-01',
            leverage=2.0
        )

        mock_deps['repo'].get_all_by_user_df.return_value = tx_df
        mock_deps['mkt'].get_ohlcv_batch.return_value = {}

        service = PerformanceService(user_id='test-user')
        result = service.reconstruct_history('test-user')

        assert not result.empty
        last_row = result.iloc[-1]
        # With leverage=2.0: cash -= (10 * 150) / 2.0 = -750
        assert last_row['cash_balance'] == -750.0, \
            f"Expected cash=-750.0, got {last_row['cash_balance']}"

    def test_mixed_leverage_transactions(self, mock_deps):
        """
        Mix of NaN and normal leverage should not cause NaN propagation.
        Simulates real scenario: old trades (NaN) + new eToro trades (1.0).
        """
        old_tx = make_tx_df(
            ticker='AAPL', action='BUY', qty=10.0, price=150.0,
            amount=1500.0, trade_date='2026-06-01',
            leverage=float('nan')
        )
        new_tx = make_tx_df(
            ticker='GOOG', action='BUY', qty=5.0, price=170.0,
            amount=850.0, trade_date='2026-06-14',
            leverage=1.0
        )
        combined = pd.concat([old_tx, new_tx], ignore_index=True)

        mock_deps['repo'].get_all_by_user_df.return_value = combined
        mock_deps['mkt'].get_ohlcv_batch.return_value = {}

        service = PerformanceService(user_id='test-user')
        result = service.reconstruct_history('test-user')

        assert not result.empty
        last_row = result.iloc[-1]
        assert not pd.isna(last_row['total_nlv']), "NLV should not be NaN"
        assert not pd.isna(last_row['cash_balance']), "Cash should not be NaN"
        assert not pd.isna(last_row['pnl']), "PnL should not be NaN"
        # Cash: -(10*150)/1.0 - (5*170)/1.0 = -1500 - 850 = -2350
        assert last_row['cash_balance'] == -2350.0, \
            f"Expected cash=-2350.0, got {last_row['cash_balance']}"