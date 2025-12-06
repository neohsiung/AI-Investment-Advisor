import pytest
from unittest.mock import MagicMock, patch
from src.workflow import run_workflow

@patch('src.workflow.MomentumAgent')
@patch('src.workflow.FundamentalAgent')
@patch('src.workflow.MacroAgent')
@patch('src.workflow.CIOAgent')
@patch('src.workflow.MarketDataService')
@patch('src.workflow.init_db')
@patch('src.database.get_db_connection')
@patch('pandas.read_sql')
@patch('src.analytics.LeverageCalculator')
@patch('src.analytics.SnapshotRecorder')
@patch('src.notifier.EmailNotifier')
def test_run_workflow_weekly(mock_notifier, mock_recorder, mock_calc, mock_read_sql, mock_db_conn, mock_init, mock_market, mock_cio, mock_macro, mock_fund, mock_mom):
    # Setup mocks
    mock_df = MagicMock()
    mock_df.empty = False
    mock_df.__getitem__.return_value.tolist.return_value = ['AAPL']
    mock_read_sql.return_value = mock_df
    
    mock_market_instance = mock_market.return_value
    mock_market_instance.get_current_prices.return_value = {'AAPL': 150.0}
    mock_market_instance.get_technical_indicators.return_value = {'rsi': 50}
    
    mock_mom_instance = mock_mom.return_value
    mock_mom_instance.run.return_value = "HOLD"
    
    mock_cio_instance = mock_cio.return_value
    mock_cio_instance.run.return_value = "Final Report"
    
    # Run workflow in weekly mode
    run_workflow(mode='weekly', dry_run=True)
    
    # Verify interactions
    mock_init.assert_called_once()
    mock_market_instance.get_current_prices.assert_called_with(['AAPL'])
    mock_mom_instance.run.assert_called()
    mock_macro.return_value.run.assert_called()
    mock_fund.return_value.run.assert_called()
    mock_cio_instance.run.assert_called()
    
    # Verify snapshot recorded
    # Line 172: if not dry_run: record_daily_snapshot
    mock_recorder.return_value.record_daily_snapshot.assert_not_called()
    
@patch('src.workflow.MomentumAgent')
@patch('src.workflow.FundamentalAgent')
@patch('src.workflow.MacroAgent')
@patch('src.workflow.CIOAgent')
@patch('src.workflow.MarketDataService')
@patch('src.workflow.init_db')
@patch('src.database.get_db_connection')
@patch('pandas.read_sql')
def test_run_workflow_daily_no_change(mock_read_sql, mock_db_conn, mock_init, mock_market, mock_cio, mock_macro, mock_fund, mock_mom):
    # Setup mocks
    mock_df = MagicMock()
    mock_df.empty = False
    mock_df.__getitem__.return_value.tolist.return_value = ['AAPL']
    mock_read_sql.return_value = mock_df
    
    mock_market_instance = mock_market.return_value
    mock_market_instance.get_current_prices.return_value = {'AAPL': 150.0}
    
    mock_mom_instance = mock_mom.return_value
    mock_mom_instance.run.return_value = "HOLD" # No significant change
    
    # Run workflow in daily mode
    run_workflow(mode='daily', dry_run=True)
    
    # Verify interactions
    mock_mom_instance.run.assert_called()
    mock_macro.return_value.run.assert_not_called()
    mock_fund.return_value.run.assert_not_called()
    mock_cio.return_value.run.assert_not_called()

@patch('src.workflow.MomentumAgent')
@patch('src.workflow.FundamentalAgent')
@patch('src.workflow.MacroAgent')
@patch('src.workflow.CIOAgent')
@patch('src.workflow.MarketDataService')
@patch('src.workflow.init_db')
@patch('src.database.get_db_connection')
@patch('pandas.read_sql')
@patch('src.analytics.LeverageCalculator')
def test_run_workflow_daily_with_change(mock_calc, mock_read_sql, mock_db_conn, mock_init, mock_market, mock_cio, mock_macro, mock_fund, mock_mom):
    # Setup mocks
    mock_df = MagicMock()
    mock_df.empty = False
    mock_df.__getitem__.return_value.tolist.return_value = ['AAPL']
    mock_read_sql.return_value = mock_df
    
    mock_market_instance = mock_market.return_value
    mock_market_instance.get_current_prices.return_value = {'AAPL': 150.0}
    
    mock_mom_instance = mock_mom.return_value
    mock_mom_instance.run.return_value = "BUY AAPL" # Significant change
    
    mock_cio_instance = mock_cio.return_value
    mock_cio_instance.run.return_value = "Final Report"
    
    # Run workflow in daily mode
    run_workflow(mode='daily', dry_run=True)
    
    # Verify interactions
    mock_mom_instance.run.assert_called()
    mock_cio_instance.run.assert_called()
