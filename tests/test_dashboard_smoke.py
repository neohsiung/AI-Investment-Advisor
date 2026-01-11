import pytest
from unittest.mock import MagicMock, patch
import sys
import importlib

# Mock external dependencies
sys.modules["streamlit"] = MagicMock()
sys.modules["plotly.express"] = MagicMock()
# Create a mock for components.v1 that acts like a module
mock_components = MagicMock()
sys.modules["streamlit.components.v1"] = mock_components
sys.modules["streamlit.components.v1.components"] = MagicMock() # Fix for "not a package" or import error
# Also ensure likely sub-imports work if needed, though mostly attributes are accessed.
# If something does `from streamlit.components.v1 import components`, this should work if we set it up right.
# But usually usage is `import streamlit.components.v1 as components`.
# Attempt to handle potential `html` or `iframe` usage
mock_components.html = MagicMock()

def test_dashboard_logic():
    """
    Test that dashboard can be imported and main() logic executed without errors.
    """
    with patch('src.data.database.get_db_connection') as mock_conn, \
         patch('pandas.read_sql') as mock_read_sql, \
         patch('src.services.market_data_service.MarketDataService') as mock_market, \
         patch('src.services.analytics_service.LeverageCalculator') as mock_calc, \
         patch('src.services.analytics_service.ROIEngine') as mock_roi, \
         patch('src.services.analytics_service.PnLCalculator') as mock_pnl, \
         patch('src.services.analytics_service.update_daily_snapshot') as mock_update, \
         patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file') as mock_flow_cls, \
         patch('src.services.transaction_service.TransactionService') as mock_trans_service, \
         patch('src.repositories.transaction_repository.SqliteTransactionRepository') as mock_trans_repo, \
         patch('src.auth.auth_manager') as mock_auth_manager: # Patch global auth_manager

        # Setup mocks
        mock_auth_manager.check_login.return_value = "AUTHENTICATED"
        mock_auth_manager.get_current_user.return_value = {'email': 'test@example.com', 'name': 'Tester'}

        # Setup mocks
        mock_flow_cls.return_value = MagicMock()
        mock_read_sql.return_value.empty = False
        # Use real DataFrame to support copy(), apply(), groupby()
        import pandas as pd
        mock_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'action': ['BUY'],
            'quantity': [10.0],
            'price': [150.0],
            'amount': [1500.0]
        })
        mock_read_sql.return_value = mock_df
        
        # Mock TransactionService returning dataframe
        mock_trans_service.return_value.get_transactions.return_value = mock_df

        mock_market.return_value.get_current_prices.return_value = {'AAPL': 150}

        mock_calc.return_value.calculate_metrics.return_value = {
            'nlv': 10000, 'cash_balance': 5000, 'leverage_ratio': 1.0, 'tnv': 5000
        }
        mock_roi.return_value.calculate_roi.return_value = 10.0
        mock_pnl.return_value.calculate_breakdown.return_value = {
            'realized': 100, 'unrealized': 200, 'total': 300
        }

        # Import and run
        try:
            from src import dashboard
            importlib.reload(dashboard) # Ensure fresh reload
            
            if hasattr(dashboard, 'DashboardPage'):
                page = dashboard.DashboardPage()
                # Mock DashboardService
                with patch('src.dashboard.DashboardService') as mock_dashboard_service:
                    mock_service_instance = mock_dashboard_service.return_value
                    mock_service_instance.prepare_dashboard_data.return_value = {
                        'metrics': {'nlv': 10000, 'cash_balance': 5000, 'leverage_ratio': 1.0},
                        'pnl_data': {'total': 300, 'unrealized': 200},
                        'roi': 10.0,
                        'transactions_df': mock_df,
                        'current_prices': {'AAPL': 150},
                        'positions_df': mock_df
                    }
                    
                    # Mock page methods
                    with patch.object(page, 'setup_page'), \
                         patch.object(page, 'handle_auth'), \
                         patch.object(page, 'render_sidebar'), \
                         patch.object(page, 'render_header'):
                        
                        # Manually set user since handle_auth is mocked
                        page.user = {'email': 'test@example.com', 'name': 'Tester'}
                        
                        page.render() # Call render directly to trigger calculation logic
                        
                        # Verify dashboard service was used
                        mock_service_instance.prepare_dashboard_data.assert_called_once()
            else:
                pytest.fail("Dashboard module missing DashboardPage class")
        except Exception as e:
            pytest.fail(f"Dashboard execution failed: {e}")
