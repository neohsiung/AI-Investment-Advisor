
import pytest
from unittest.mock import MagicMock, patch, call
from src.workflow import run_workflow

# Common Mocks Setup
@pytest.fixture
def mock_common_deps():
    with patch('src.workflow.MomentumAgent') as mock_mom, \
         patch('src.workflow.FundamentalAgent') as mock_fund, \
         patch('src.workflow.MacroAgent') as mock_macro, \
         patch('src.workflow.CIOAgent') as mock_cio, \
         patch('src.workflow.MarketDataService') as mock_market, \
         patch('src.workflow.init_db') as mock_init, \
         patch('src.data.database.get_db_connection') as mock_db_conn, \
         patch('pandas.read_sql') as mock_read_sql, \
         patch('src.analytics.LeverageCalculator') as mock_calc, \
         patch('src.analytics.SnapshotRecorder') as mock_recorder, \
         patch('src.notifier.EmailNotifier') as mock_notifier, \
         patch('src.services.fred_service.FredService') as mock_fred:

        # Default DB behavior
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__.return_value.tolist.return_value = ['AAPL']
        mock_read_sql.return_value = mock_df

        # Default Market Data
        mock_market_instance = mock_market.return_value
        mock_market_instance.get_current_prices.return_value = {'AAPL': 150.0}
        mock_market_instance.get_technical_indicators.return_value = {'rsi': 50}
        mock_market_instance.get_macro_data.return_value = {'market_macro': 'data'}
        mock_market_instance.get_financials.return_value = 'financials'
        mock_market_instance.get_news.return_value = 'news'
        
        # Default Fred Service
        mock_fred_instance = mock_fred.return_value
        mock_fred_instance.get_macro_indicators.return_value = {'gdp': 2.0}

        # Default Agents Freshness (Always Fresh)
        mock_mom.return_value.check_freshness.return_value = (True, "hash", None)
        mock_fund.return_value.check_freshness.return_value = (True, "hash", None)
        mock_macro.return_value.check_freshness.return_value = (True, "hash", None)
        mock_cio.return_value.check_freshness.return_value = (True, "hash", None)

        # CIO run return values (Mocking side_effect for different modes)
        def cio_side_effect(context, mode=None):
            if mode == 'strategy':
                return {"sector_strategy": {"Tech": "Overweight"}, "candidates": ["GOOGL"]}
            return "Final CIO Report Content"
        
        mock_cio.return_value.run.side_effect = cio_side_effect
        mock_mom.return_value.run.return_value = "Momentum Analysis"
        mock_fund.return_value.run.return_value = "Fundamental Analysis"
        mock_macro.return_value.run.return_value = "Macro Risk Analysis"

        yield {
            'mom': mock_mom, 'fund': mock_fund, 'macro': mock_macro, 'cio': mock_cio,
            'market': mock_market, 'init': mock_init, 'read_sql': mock_read_sql,
            'calc': mock_calc, 'recorder': mock_recorder, 'notifier': mock_notifier,
            'fred': mock_fred, 'db_conn': mock_db_conn
        }

def test_run_workflow_weekly(mock_common_deps):
    # Retrieve mocks
    mocks = mock_common_deps
    
    # Run workflow
    run_workflow(mode='weekly', dry_run=True)

    # Verifications
    mocks['init'].assert_called_once()
    
    # 1. Macro Analysis
    mocks['macro'].return_value.run.assert_called()
    
    # 2. Strategy (CIO)
    # assert mock_cio.run called with mode='strategy'
    # It might be called twice (strategy, then report)
    assert mocks['cio'].return_value.run.call_count >= 1
    
    # 3. Deep Research (Holdings + Candidates)
    # Holdings: AAPL, Candidates: GOOGL -> Total 2
    # Momentum should run for both
    assert mocks['mom'].return_value.run.call_count >= 1
    
    # Fundamental should run (Weekly mode)
    assert mocks['fund'].return_value.run.call_count >= 1
    
    # 4. Final Report
    # verify mode='report' call
    calls = mocks['cio'].return_value.run.mock_calls
    # call(context, mode='strategy'), call(context, mode='report')
    # Check if 'report' mode was triggered
    has_report_call = any(c.kwargs.get('mode') == 'report' for c in calls)
    assert has_report_call

    # Snapshot not recorded because dry_run=True
    mocks['recorder'].return_value.record_daily_snapshot.assert_not_called()


def test_run_workflow_daily(mock_common_deps):
    mocks = mock_common_deps
    
    # Run workflow
    run_workflow(mode='daily', dry_run=True)
    
    # Verifications
    # Macro should run
    mocks['macro'].return_value.run.assert_called()
    
    # CIO Strategy should run
    assert mocks['cio'].return_value.run.call_count >= 1
    
    # Momentum should run
    mocks['mom'].return_value.run.assert_called()
    
    # Fundamental should NOT run (Daily mode defaults)
    # BUT, if check_freshness returns True, it runs?
    # In workflow.py: if mode == 'weekly' or force_report: run fundamental.
    # So in daily, it splits.
    mocks['fund'].return_value.run.assert_not_called()
    
    # Final Report
    has_report_call = any(c.kwargs.get('mode') == 'report' for c in mocks['cio'].return_value.run.mock_calls)
    assert has_report_call


def test_run_workflow_force_report(mock_common_deps):
    mocks = mock_common_deps
    # Force report = True
    run_workflow(mode='daily', dry_run=True, force_report=True)
    
    # Fundamental should run because force_report overrides daily mode skip?
    # Workflow logic: if mode == 'weekly' or force_report: ...
    mocks['fund'].return_value.run.assert_called()
