import pytest
from unittest.mock import MagicMock, patch
from src.services.transaction_service import TransactionService
import pandas as pd

@pytest.fixture
def mock_repo():
    return MagicMock()

def test_get_transactions(mock_repo):
    service = TransactionService(user_id="user1", repository=mock_repo)
    
    mock_df = pd.DataFrame([{"id": 1}])
    mock_repo.get_all_by_user_df.return_value = mock_df
    
    # Test specific user
    df = service.get_transactions("user2")
    mock_repo.get_all_by_user_df.assert_called_with("user2")
    assert not df.empty
    
    # Test default user
    df = service.get_transactions()
    mock_repo.get_all_by_user_df.assert_called_with("user1")

def test_get_user_tickers(mock_repo):
    service = TransactionService(user_id="user1", repository=mock_repo)
    
    mock_repo.get_unique_tickers.return_value = ["AAPL", "GOOG"]
    mock_repo.get_active_tickers.return_value = ["AAPL"]
    
    # Test all tickers
    tickers = service.get_user_tickers("user1", only_active=False)
    assert tickers == ["AAPL", "GOOG"]
    
    # Test active tickers
    active = service.get_user_tickers("user1", only_active=True)
    assert active == ["AAPL"]

def test_add_manual_trade(mock_repo):
    with patch('src.services.transaction_service.update_daily_snapshot') as mock_update:
        service = TransactionService(user_id="user1", repository=mock_repo)
        
        # Success Case
        success, msg = service.add_manual_trade("AAPL", "2023-01-01", "BUY", 10, 150, 5)
        
        assert success is True
        mock_repo.add.assert_called_with(
             user_id="user1", ticker="AAPL", date="2023-01-01", 
             action="BUY", quantity=10, price=150, fees=5
        )
        mock_update.assert_called()
        
        # Failure Case (Exception)
        mock_repo.add.side_effect = Exception("DB Error")
        success, msg = service.add_manual_trade("AAPL", "2023-01-01", "BUY", 10, 150, 5)
        assert success is False
        assert "DB Error" in msg

def test_delete_transaction(mock_repo):
    with patch('src.services.transaction_service.update_daily_snapshot') as mock_update:
        service = TransactionService(user_id="user1", repository=mock_repo)
        
        # Success
        success, msg = service.delete_transaction("tx_1")
        assert success is True
        mock_repo.delete.assert_called_with(user_id="user1", transaction_id="tx_1")
        mock_update.assert_called()
        
        # Failure
        mock_repo.delete.side_effect = Exception("Delete Error")
        success, msg = service.delete_transaction("tx_1")
        assert success is False
