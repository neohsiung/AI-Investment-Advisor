import pytest
from unittest.mock import MagicMock, patch, ANY
from src.services.performance_service import PerformanceService

@pytest.fixture
def mock_db():
    # Mock the actual import location
    with patch('src.data.database.get_db_connection') as mock:
        yield mock

def test_record_recommendation(mock_db):
    service = PerformanceService(user_id="test_user")
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    mock_db.return_value.__exit__.return_value = None
    
    service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)
    
    mock_conn.execute.assert_called()
    mock_conn.commit.assert_called()

def test_get_agent_performance(mock_db):
    service = PerformanceService(user_id="test_user")
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    mock_db.return_value.__exit__.return_value = None
    
    # Mock pandas read_sql return
    import pandas as pd
    # Simulate the actual DataFrame that would be returned by read_sql
    mock_df = pd.DataFrame([
        {"agent": "Momentum", "id": "1", "ticker": "AAPL", "signal": "BUY"},
        {"agent": "Momentum", "id": "2", "ticker": "TSLA", "signal": "BUY"},
        {"agent": "Fundamental", "id": "3", "ticker": "AAPL", "signal": "HOLD"},
    ])
    
    with patch('pandas.read_sql', return_value=mock_df):
        stats = service.get_agent_performance()
        
        # Match actual implementation which returns list of dicts after groupby
        assert len(stats) == 2
        # Check both agents exist (don't assume order)
        agents = {s["agent"]: s["count"] for s in stats}
        assert agents.get("Momentum") == 2  # 2 recommendations
        assert agents.get("Fundamental") == 1  # 1 recommendation

def test_record_recommendation_error(mock_db):
    service = PerformanceService(user_id="test_user")
    mock_db.return_value.__enter__.side_effect = Exception("DB Fail")
    
    # Should not raise
    service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)

def test_get_agent_performance_error(mock_db):
    service = PerformanceService(user_id="test_user")
    mock_db.return_value.__enter__.side_effect = Exception("DB Fail")
    
    stats = service.get_agent_performance()
    assert stats == []

