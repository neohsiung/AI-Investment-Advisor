import pytest
from unittest.mock import MagicMock, patch
import sys
import importlib

# Mock external dependencies
sys.modules["streamlit"] = MagicMock()
sys.modules["plotly.express"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()

def test_dashboard_logic():
    """
    Test that dashboard can be imported and main() logic executed without errors.
    """
    with patch('src.database.get_db_connection') as mock_conn, \
         patch('pandas.read_sql') as mock_read_sql, \
         patch('src.market_data.MarketDataService') as mock_market, \
         patch('src.analytics.LeverageCalculator') as mock_calc, \
         patch('src.analytics.ROIEngine') as mock_roi, \
         patch('src.analytics.PnLCalculator') as mock_pnl, \
         patch('src.analytics.update_daily_snapshot') as mock_update:
        
        # Setup mocks
        mock_read_sql.return_value.empty = False
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__.return_value.tolist.return_value = ['AAPL']
        mock_read_sql.return_value = mock_df
        
        mock_market.return_value.get_current_prices.return_value = {'AAPL': 150}
        
        mock_calc.return_value.calculate_metrics.return_value = {
            'nlv': 10000, 'cash_balance': 5000, 'leverage_ratio': 1.0, 'tnv': 5000
        }
        mock_roi.return_value.calculate_roi.return_value = 10.0
        mock_pnl.return_value.calculate_breakdown.return_value = {
            'realized': 100, 'unrealized': 200, 'total': 300
        }

        # Import and run main
        try:
            from src import dashboard
            importlib.reload(dashboard) # Ensure fresh reload
            if hasattr(dashboard, 'main'):
                dashboard.main()
            else:
                pytest.fail("Dashboard module missing main() function")
        except Exception as e:
            pytest.fail(f"Dashboard failed to run: {e}")
            
        # Verify interactions
        mock_update.assert_called()
        mock_calc.return_value.calculate_metrics.assert_called()
