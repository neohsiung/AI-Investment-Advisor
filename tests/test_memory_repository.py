import pytest
from unittest.mock import MagicMock, patch
from src.repositories.memory_repository import SqliteMemoryRepository
from src.services.memory_service import ReportMemoryItem

@pytest.fixture
def mock_db():
    with patch('src.repositories.memory_repository.get_db_connection') as mock_conn:
        mock_db_instance = MagicMock()
        mock_conn.return_value = mock_db_instance
        # mock_db_instance.__enter__.return_value = mock_db_instance 
        # get_db_connection in memory_repository does not look like it's used as a context manager based on code provided
        # It calls conn = get_db_connection() ... finally conn.close()
        # So we just mock the return value.
        yield mock_db_instance

def test_save_report(mock_db):
    repo = SqliteMemoryRepository()
    
    item = ReportMemoryItem(
        user_id="user123",
        report_type="daily",
        report_date="2026-01-01",
        full_content="Today is a good day.",
        compressed_summary="Good day."
    )
    
    repo.save_report(item)
    
    # Verify execute was called with correct INSERT
    mock_db.execute.assert_called()
    args, kwargs = mock_db.execute.call_args
    sql = str(args[0])
    params = args[1]
    
    assert "INSERT INTO reports" in sql
    assert params["uid"] == "user123"
    assert params["content"] == "Today is a good day."
    assert params["rtype"] == "daily"
    
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()

def test_get_recent_reports(mock_db):
    repo = SqliteMemoryRepository()
    
    # Mock return rows
    # Rows structure per code: id, user_id, date, content, summary, report_type
    mock_rows = [
        ("id1", "user123", "2026-01-02", "Newer report", "Short Summary 1", "daily"),
        ("id2", "user123", "2026-01-01", "Older report", "Short Summary 2", "daily")
    ]
    mock_db.execute.return_value.fetchall.return_value = mock_rows
    
    items = repo.get_recent_reports("user123", "daily", limit=5)
    
    assert len(items) == 2
    assert items[0].user_id == "user123"
    assert items[0].full_content == "Newer report"
    assert items[0].report_date == "2026-01-02"
    
    # Verify SQL
    args, kwargs = mock_db.execute.call_args
    sql = str(args[0])
    params = args[1]
    
    assert "SELECT" in sql
    assert "FROM reports" in sql
    assert params["uid"] == "user123"
    assert params["limit"] == 5

def test_save_report_error_handling(mock_db):
    repo = SqliteMemoryRepository()
    mock_db.execute.side_effect = Exception("DB Error")
    
    item = ReportMemoryItem(
        user_id="u", report_type="t", report_date="d", full_content="c"
    )
    
    # Should not raise exception, just print error (as per implementation)
    repo.save_report(item) 
    
    mock_db.close.assert_called_once()

def test_get_recent_reports_error_handling(mock_db):
    repo = SqliteMemoryRepository()
    mock_db.execute.side_effect = Exception("DB Error")
    
    items = repo.get_recent_reports("u", "t", 10)
    assert items == []
    mock_db.close.assert_called_once()
