import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from src.analytics import LeverageCalculator, SnapshotRecorder, update_daily_snapshot

@pytest.fixture
def mock_db_connection():
    with patch('src.analytics.get_db_connection') as mock_conn:
        mock_db = MagicMock()
        mock_conn.return_value = mock_db
        yield mock_db

def test_leverage_calculator_metrics(mock_db_connection):
    calc = LeverageCalculator()
    
    # Mock pd.read_sql for positions
    # Return DataFrame: ticker, net_qty
    df_positions = pd.DataFrame([
        {"ticker": "AAPL", "net_qty": 10.0},
        {"ticker": "SPY", "net_qty": 5.0}
    ])
    
    # Mock pd.read_sql for cash_flows (used in NLV calc part 2) 
    # and transactions (used in NLV calc part 2)
    # The calculator calls read_sql twice: 1. transactions(grouped), 2. transactions(all)
    
    with patch('src.analytics.pd.read_sql') as mock_read_sql:
        # We need to handle multiple calls to read_sql. 
        # 1st call: positions (Grouped)
        # 2nd call: transactions (For cash impact)
        
        # Side effect sequence
        mock_read_sql.side_effect = [
            df_positions, # positions
            pd.DataFrame([{"action": "DEPOSIT", "amount": 10000.0}]) # transactions for cash calc
        ]
        
        # Mock cash_query fetchone (for cash_flows table sum)
        mock_db_connection.execute.return_value.fetchone.return_value = (None,) # Assume no cash_flows entries, only transactions? 
        # Wait, the code queries cash_flows table first.
        # Let's say cash_flows sum is 0.
        
        prices = {"AAPL": 150.0, "SPY": 400.0}
        user_id = "user1"
        
        metrics = calc.calculate_metrics(prices, user_id)
        
        # TNV = (10*150) + (5*400) = 1500 + 2000 = 3500
        # Cash Flow Sum = 0 (mocked None)
        # Transaction Cash Impact (DEPOSIT 10000) -> logic: if DEPOSIT, +amount.
        # Check source: elif action == 'DEPOSIT': trans_cash_impact += amount
        # So Cash = 0 + 10000 = 10000
        # NLV = 10000 + 3500 = 13500
        # Lev = 3500 / 13500 = 0.259...
        
        assert metrics['tnv'] == 3500.0
        assert metrics['cash_balance'] == 10000.0
        assert metrics['nlv'] == 13500.0
        assert 0.25 < metrics['leverage_ratio'] < 0.27

def test_snapshot_recorder(mock_db_connection):
    recorder = SnapshotRecorder()
    
    # Mock fetchone for invested capital
    mock_db_connection.execute.return_value.fetchone.return_value = (5000.0,)
    
    recorder.record_daily_snapshot(nlv=10000.0, cash_balance=5000.0, user_id="user1", total_tnv=5000.0, leverage_ratio=0.5)
    
    mock_db_connection.execute.assert_called()
    assert mock_db_connection.commit.called

def test_update_daily_snapshot_integration(mock_db_connection):
    # Mock pd.read_sql for active tickers
    df_tickers = pd.DataFrame([{"ticker": "AAPL", "net_qty": 5.0}])
    
    with patch('src.analytics.pd.read_sql', return_value=df_tickers), \
         patch('src.analytics.MarketDataService') as MockMarket, \
         patch('src.analytics.LeverageCalculator') as MockCalc, \
         patch('src.analytics.SnapshotRecorder') as MockRecorder:
        
        MockMarket.return_value.get_current_prices.return_value = {"AAPL": 100.0}
        
        MockCalc.return_value.calculate_metrics.return_value = {
            "tnv": 500, "nlv": 1000, "cash_balance": 500, "leverage_ratio": 0.5
        }
        
        update_daily_snapshot("db.sqlite", "user1")
        
        MockMarket.return_value.get_current_prices.assert_called_with(["AAPL"])
        MockCalc.return_value.calculate_metrics.assert_called()
        MockRecorder.return_value.record_daily_snapshot.assert_called_with(
            1000, 500, "user1", total_tnv=500, leverage_ratio=0.5
        )

from src.analytics import ROIEngine, PnLCalculator

def test_roi_engine(mock_db_connection):
    engine = ROIEngine()
    
    # Mock net invested capital (Deposits - Withdrawals)
    # Query returns (Sum, )
    mock_db_connection.execute.return_value.fetchone.return_value = (5000.0,)
    
    # ROI = (NLV - Invested) / Invested
    # NLV = 6000, Invested = 5000 -> Profit = 1000 -> ROI = 20%
    roi = engine.calculate_roi(nlv=6000.0, user_id="user1")
    
    assert roi == 20.0
    
    # Test zero invested
    mock_db_connection.execute.return_value.fetchone.return_value = (0.0,)
    roi_zero = engine.calculate_roi(nlv=6000.0, user_id="user1")
    assert roi_zero == 0.0

def test_pnl_calculator(mock_db_connection):
    calc = PnLCalculator()
    
    # Mock transactions
    # Columns: ticker, action, quantity, price, fees
    data = [
        {"ticker": "AAPL", "action": "BUY", "quantity": 10.0, "price": 100.0, "fees": 0.0},
        {"ticker": "AAPL", "action": "SELL", "quantity": 5.0, "price": 120.0, "fees": 0.0}, # Realized +100
        {"ticker": "GOOG", "action": "BUY", "quantity": 10.0, "price": 200.0, "fees": 0.0}
    ]
    df_trans = pd.DataFrame(data)
    
    with patch('src.analytics.pd.read_sql', return_value=df_trans):
        current_prices = {"AAPL": 130.0, "GOOG": 210.0}
        
        breakdown = calc.calculate_breakdown(current_prices, "user1")
        
        # AAPL:
        # Buy 10 @ 100. Avg Cost = 100.
        # Sell 5 @ 120. Realized = (120-100)*5 = 100.
        # Remaining 5. Avg Cost 100.
        # Current Price 130. Unrealized = (130-100)*5 = 150.
        # Total AAPL PnL = 100 + 150 = 250.
        
        # GOOG:
        # Buy 10 @ 200. Cost 200.
        # Price 210. Unrealized = (210-200)*10 = 100.
        # Realized = 0.
        
        # Totals:
        # Realized = 100
        # Unrealized = 150 + 100 = 250
        # Total = 350
        
        assert breakdown['realized'] == 100.0
        assert breakdown['unrealized'] == 250.0
        assert breakdown['total'] == 350.0
        assert breakdown['details']['AAPL']['realized'] == 100.0
        assert breakdown['details']['AAPL']['unrealized'] == 150.0
