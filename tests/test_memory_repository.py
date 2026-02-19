
import pytest
from unittest.mock import MagicMock, patch
from src.repositories.memory_repository import AlchemyMemoryRepository
from src.services.memory_service import ReportMemoryItem

@pytest.fixture
def mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    # Mock engine.connect() context manager
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    # Mock engine.begin() context manager
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    return mock_engine, mock_conn

def test_save_report(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    
    item = ReportMemoryItem(
        user_id="user123",
        report_type="daily",
        report_date="2026-01-01",
        full_content="Today is a good day.",
        compressed_summary="Good day."
    )
    
    repo.save_report(item)
    
    # Verify execute was called
    assert conn.execute.called
    args, kwargs = conn.execute.call_args
    params = kwargs.get('parameters') or args[1]
    
    assert params["uid"] == "user123"
    assert params["content"] == "Today is a good day."
    assert params["rtype"] == "daily"

def test_get_recent_reports(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    
    # Mock return rows
    mock_row = MagicMock()
    mock_row.user_id = "user123"
    mock_row.report_type = "daily"
    mock_row.date = "2026-01-02"
    mock_row.content = "Newer report"
    mock_row.summary = "Short Summary 1"
    
    conn.execute.return_value.fetchall.return_value = [mock_row]
    
    items = repo.get_recent_reports("user123", "daily", limit=5)
    
    assert len(items) == 1
    assert items[0].user_id == "user123"
    assert items[0].full_content == "Newer report"
    
    # Verify SQL params
    args, kwargs = conn.execute.call_args
    params = kwargs.get('parameters') or args[1]
    assert params["uid"] == "user123"
    assert params["limit"] == 5

def test_save_report_error_handling(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    conn.execute.side_effect = Exception("DB Error")
    
    item = ReportMemoryItem(
        user_id="u", report_type="t", report_date="d", full_content="c"
    )
    
    # AlchemyMemoryRepository uses engine.begin(), it will raise if execute fails
    with pytest.raises(Exception):
        repo.save_report(item)

def test_get_recent_reports_error_handling(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    conn.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(Exception):
        repo.get_recent_reports("u", "t", 10)
