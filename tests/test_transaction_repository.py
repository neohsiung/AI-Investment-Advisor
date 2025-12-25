import pytest
from unittest.mock import MagicMock, patch
from src.repositories.transaction_repository import SqliteTransactionRepository

@pytest.fixture
def mock_db():
    with patch('src.repositories.transaction_repository.get_db_connection') as mock_conn:
        mock_db_instance = MagicMock()
        mock_conn.return_value = mock_db_instance
        mock_db_instance.__enter__.return_value = mock_db_instance # Context manager
        yield mock_db_instance

def test_add_transaction(mock_db):
    repo = SqliteTransactionRepository()
    
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
    
    mock_db.execute.assert_called()
    mock_db.commit.assert_called()
    
    # Check SQL params in call args
    args, kwargs = mock_db.execute.call_args
    sql = args[0]
    params = args[1]
    
    assert "INSERT INTO transactions" in str(sql)
    assert params['user_id'] == "user1"
    assert params['ticker'] == "AAPL"

def test_get_unique_tickers(mock_db):
    repo = SqliteTransactionRepository()
    
    # Mock result
    mock_db.execute.return_value.fetchall.return_value = [("AAPL",), ("GOOG",)]
    
    tickers = repo.get_unique_tickers("user1")
    
    assert len(tickers) == 2
    assert "AAPL" in tickers
    assert "GOOG" in tickers
    mock_db.execute.assert_called()

def test_get_all_by_user(mock_db):
    repo = SqliteTransactionRepository()
    
    # Mock fetchall returning mock rows
    mock_db.execute.return_value.fetchall.return_value = []
    
    txs = repo.get_all_by_user("user1")
    assert txs == []
    
    mock_db.execute.assert_called()

def test_delete_transaction(mock_db):
    repo = SqliteTransactionRepository()
    repo.delete(user_id="user1", transaction_id="tx_id_1")
    # Called twice (transactions and cash_flows)
    assert mock_db.execute.call_count >= 1
    mock_db.commit.assert_called()
