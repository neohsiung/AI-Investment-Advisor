import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock, patch
from src.data.ingestors.strategies import SimpleIngestor, RobinhoodIngestor, IBKRIngestor

@pytest.fixture
def mock_db_conn():
    with patch("src.data.ingestors.strategies.get_db_connection") as mock_conn_ctx:
        mock_conn = MagicMock()
        mock_trans = MagicMock()
        # Context manager behavior
        mock_conn_ctx.return_value.__enter__.return_value = mock_conn
        mock_conn.begin.return_value.__enter__.return_value = mock_trans
        yield mock_conn

def test_simple_ingestor_ingest(mock_db_conn):
    df = pd.DataFrame([{
        'Date': '2023-01-01',
        'Ticker': 'AAPL',
        'Action': 'BUY',
        'Quantity': 10,
        'Price': 150.0
    }])
    ingestor = SimpleIngestor(db_path="test.db")
    ingestor.ingest(df, user_id="user1")
    
    # Check if execute was called
    assert mock_db_conn.execute.called
    args, kwargs = mock_db_conn.execute.call_args
    params = args[1]
    assert params['ticker'] == 'AAPL'
    assert params['quantity'] == 10.0
    assert params['user_id'] == 'user1'

def test_robinhood_ingestor_ingest(mock_db_conn):
    ingestor = RobinhoodIngestor("db")
    df = pd.DataFrame([{
        'date': '2023-01-01',
        'symbol': 'TSLA',
        'side': 'buy',
        'quantity': 5,
        'price': 200.0,
        'state': 'filled'
    }])
    ingestor.ingest(df, user_id="user2")
    
    assert mock_db_conn.execute.called
    args, kwargs = mock_db_conn.execute.call_args
    params = args[1]
    assert params['ticker'] == 'TSLA'
    assert params['action'] == 'BUY'
    assert params['amount'] == 1000.0

def test_ibkr_ingestor_ingest(mock_db_conn):
    ingestor = IBKRIngestor("db")
    df = pd.DataFrame([{
        'Date/Time': '2023-01-01, 10:00:00',
        'Symbol': 'NVDA',
        'Type': 'Trade',
        'Quantity': 2,
        'T. Price': 400.0,
        'Comm/Fee': -1.0
    }])
    ingestor.ingest(df, user_id="user3")
    
    assert mock_db_conn.execute.called
    args, kwargs = mock_db_conn.execute.call_args
    params = args[1]
    assert params['ticker'] == 'NVDA'
    assert params['action'] == 'BUY'
    assert params['fees'] == 1.0 # Absolute value
