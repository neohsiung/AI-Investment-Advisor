import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from src.services.performance_service import PerformanceService
from datetime import datetime, timedelta

def test_reconstruct_history_handles_dict_ohlcv():
    service = PerformanceService(user_id="test_user")
    service.market_service = MagicMock()
    
    # 1. Mock Transactions
    mock_transactions = pd.DataFrame([
        {
            "trade_date": (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 10,
            "price": 150.0,
            "fees": 0,
            "amount": -1500.0,
            "account_id": ""
        }
    ])
    
    # Mocking transaction retrieval
    # Note: reconstruct_history calls get_all_by_user_df on its repository
    service.trans_repo = MagicMock()
    service.trans_repo.get_all_by_user_df.return_value = mock_transactions
    
    # 2. Mock MarketDataService to return DICT format (the current standard)
    mock_ohlcv = {
        "AAPL": {
            "date": [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(5, -1, -1)],
            "close": [140.0, 145.0, 150.0, 155.0, 160.0, 165.0]
        }
    }
    service.market_service.get_ohlcv_batch.return_value = mock_ohlcv
    
    # 3. Call reconstruct_history
    # This should NOT raise AttributeError
    history_df = service.reconstruct_history("test_user")
    print(f"DEBUG: history_df shape: {history_df.shape}")
    if history_df.empty:
        print("DEBUG: history_df is empty!")
    
    assert not history_df.empty, "history_df should not be empty"
    assert "total_nlv" in history_df.columns

if __name__ == "__main__":
    test_reconstruct_history_handles_dict_ohlcv()
