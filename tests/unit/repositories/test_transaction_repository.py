import pytest
from unittest.mock import MagicMock, patch
from src.repositories.transaction_repository import (
    AlchemyTransactionRepository,
    ENTRY_CATEGORY_TRADE,
    ENTRY_CATEGORY_CAPITAL_FLOW,
    ENTRY_CATEGORY_SYNC_ADJUSTMENT,
)

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

def test_add_transaction_with_entry_category(mock_conn):
    repo = AlchemyTransactionRepository()
    
    # Real deposit should be tagged capital_flow
    repo.add(
        user_id="user1",
        ticker="CASH",
        action="DEPOSIT",
        quantity=1,
        price=1000.0,
        date="2023-01-01",
        fees=0.0,
        entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
    )
    
    call_args = mock_conn.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["entry_category"] == ENTRY_CATEGORY_CAPITAL_FLOW

def test_add_transaction_sync_adjustment(mock_conn):
    repo = AlchemyTransactionRepository()
    
    # ETORO_SYNC entry should be tagged sync_adjustment
    repo.add(
        user_id="user1",
        ticker="CASH",
        action="DEPOSIT",
        quantity=1,
        price=50.0,
        date="2023-01-01",
        fees=0.0,
        source_file="ETORO_SYNC",
        entry_category=ENTRY_CATEGORY_SYNC_ADJUSTMENT,
    )
    
    call_args = mock_conn.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["entry_category"] == ENTRY_CATEGORY_SYNC_ADJUSTMENT
    
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

def test_calculate_net_invested_capital_uses_entry_category(mock_conn):
    """Verify the SQL uses entry_category = 'capital_flow', not a ticker blacklist."""
    repo = AlchemyTransactionRepository()
    mock_conn.execute.return_value.fetchone.return_value = (5000.0,)
    
    repo.calculate_net_invested_capital("user1")
    
    called_sql = str(mock_conn.execute.call_args[0][0])
    assert "entry_category" in called_sql, "SQL must filter by entry_category"
    assert "capital_flow" in called_sql, "SQL must filter for capital_flow entries only"
    # The old fragile ticker blacklist should NOT be present
    assert "ETORO_SYNC" not in called_sql, "SQL must not use the deprecated ticker blacklist"

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
