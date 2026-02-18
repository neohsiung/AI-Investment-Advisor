import pytest
from unittest.mock import MagicMock, patch
from src.repositories.transaction_repository import AlchemyTransactionRepository

@pytest.fixture
def mock_engine():
    mock_eng = MagicMock()
    with patch('src.repositories.transaction_repository.get_db_engine', return_value=mock_eng):
        yield mock_eng

@pytest.fixture
def mock_conn(mock_engine):
    conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = conn
    mock_engine.begin.return_value.__enter__.return_value = conn
    return conn

def test_add_transaction(mock_conn):
    repo = AlchemyTransactionRepository()
    
    # Test adding a transaction
    repo.add(
        user_id="user1", 
        ticker="AAPL", 
        action="BUY", 
        quantity=10, 
        price=150.0, 
        date="2023-01-01", 
        fees=5.0
    )
    
    mock_conn.execute.assert_called()
    
def test_get_all_by_user(mock_conn):
    repo = AlchemyTransactionRepository()
    
    # Mock fetchall returning mock rows
    mock_conn.execute.return_value.fetchall.return_value = []
    
    txs = repo.get_all_by_user("user1")
    assert txs == []
    
    mock_conn.execute.assert_called()

def test_delete_transaction(mock_conn):
    repo = AlchemyTransactionRepository()
    repo.delete(user_id="user1", transaction_id="tx_id_1")
    assert mock_conn.execute.call_count >= 1

def test_get_cash_flow_sum(mock_conn):
    repo = AlchemyTransactionRepository()
    mock_conn.execute.return_value.fetchone.return_value = (5000.0,)
    
    result = repo.get_cash_flow_sum("user1")
    assert result == 5000.0
    
    mock_conn.execute.return_value.fetchone.return_value = (None,)
    assert repo.get_cash_flow_sum("user1") == 0.0

def test_calculate_net_invested_capital(mock_conn):
    repo = AlchemyTransactionRepository()
    mock_conn.execute.return_value.fetchone.return_value = (10000.0,)
    
    result = repo.calculate_net_invested_capital("user1")
    assert result == 10000.0

def test_get_active_tickers(mock_conn):
    repo = AlchemyTransactionRepository()
    # Mock [(ticker,), (ticker,)]
    mock_conn.execute.return_value.fetchall.return_value = [("AAPL",), ("TSLA",)]
    
    tickers = repo.get_active_tickers("user1")
    assert tickers == ["AAPL", "TSLA"]

def test_get_holdings_summary(mock_conn):
    repo = AlchemyTransactionRepository()
    # Mock [(ticker, qty), (ticker, qty)]
    mock_conn.execute.return_value.fetchall.return_value = [("AAPL", 10.0), ("TSLA", 5.0)]
    
    summary = repo.get_holdings_summary("user1")
    assert len(summary) == 2
    assert summary[0] == ("AAPL", 10.0)

def test_get_latest_leverage(mock_conn):
    repo = AlchemyTransactionRepository()
    mock_conn.execute.return_value.fetchone.return_value = (1.5,)
    
    lev = repo.get_latest_leverage("user1")
    assert lev == 1.5
    
    mock_conn.execute.return_value.fetchone.return_value = None
    assert repo.get_latest_leverage("user1") == 1.0
