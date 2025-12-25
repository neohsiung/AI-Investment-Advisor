import pytest
from unittest.mock import MagicMock, patch
from src.services.ingestion_service import IngestionService

@pytest.fixture
def mock_ingestor():
    with patch('src.services.ingestion_service.TradeIngestor') as MockIngestor:
        yield MockIngestor

@pytest.fixture
def service(mock_ingestor):
    return IngestionService(db_path="test.db", user_id="user1")

def test_process_csv_upload_success(service, mock_ingestor):
    # Mock file buffer
    mock_file = MagicMock()
    mock_file.getbuffer.return_value = b"test content"
    
    # Mock open
    with patch("builtins.open", new_callable=MagicMock), \
         patch("os.remove") as mock_remove, \
         patch("os.path.exists", return_value=True), \
         patch("src.services.ingestion_service.update_daily_snapshot") as mock_update:
        
        success, msg = service.process_csv_upload(mock_file, "robinhood")
        
        assert success is True
        assert "匯入成功" in msg
        mock_ingestor.return_value.ingest_csv.assert_called_with(f"temp_upload_user1.csv", "robinhood", user_id="user1")
        mock_update.assert_called()
        mock_remove.assert_called()

def test_process_csv_upload_failure(service, mock_ingestor):
    mock_file = MagicMock()
    mock_ingestor.return_value.ingest_csv.side_effect = Exception("Format Error")
    
    with patch("builtins.open", new_callable=MagicMock), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:
        
        success, msg = service.process_csv_upload(mock_file, "simple")
        
        assert success is False
        assert "Format Error" in msg
        mock_remove.assert_called()
