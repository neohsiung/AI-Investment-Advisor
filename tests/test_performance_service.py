import pytest
from unittest.mock import MagicMock, patch
from src.services.performance_service import PerformanceService

@pytest.fixture
def mock_db():
    with patch('src.services.performance_service.get_db_connection') as mock:
        yield mock

def test_record_recommendation(mock_db):
    service = PerformanceService()
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)
    
    mock_conn.execute.assert_called()
    mock_conn.commit.assert_called()
    mock_conn.close.assert_called()

def test_get_agent_performance(mock_db):
    service = PerformanceService()
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    # Mock pandas read_sql return
    import pandas as pd
    mock_df = pd.DataFrame([
        {"agent": "Momentum", "total": 10, "wins": 6},
        {"agent": "Fundamental", "total": 5, "wins": 2}
    ])
    
    with patch('pandas.read_sql', return_value=mock_df):
        stats = service.get_agent_performance()
        
        assert stats["Momentum"]["win_rate"] == 0.6
        assert stats["Fundamental"]["win_rate"] == 0.4
    
    mock_conn.close.assert_called()

def test_record_recommendation_error(mock_db):
    service = PerformanceService()
    mock_db.side_effect = Exception("DB Fail")
    
    # Should not raise
    service.record_recommendation("Momentum", "AAPL", "BUY", 150.0)

def test_get_agent_performance_error(mock_db):
    service = PerformanceService()
    mock_db.side_effect = Exception("DB Fail")
    
    stats = service.get_agent_performance()
    assert stats == {}
