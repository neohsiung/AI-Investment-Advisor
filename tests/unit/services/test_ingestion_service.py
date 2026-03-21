import pytest
from unittest.mock import MagicMock, patch
from src.services.ingestion_service import IngestionService

@pytest.fixture
def mock_factory():
    with patch('src.services.ingestion_service.IngestorFactory') as MockFactory:
        yield MockFactory

@pytest.fixture
def service():
    return IngestionService(db_path="test.db", user_id="user1")

def test_process_csv_upload_success(service, mock_factory):
    # Mock file buffer
    mock_file = MagicMock()
    mock_file.getbuffer.return_value = b"test content"
    
    # Mock Ingestor
    mock_ingestor = MagicMock()
    mock_factory.get_ingestor.return_value = mock_ingestor

    # Mock open and pandas
    with patch("builtins.open", new_callable=MagicMock), \
         patch("src.services.ingestion_service.pd.read_csv") as mock_read_csv, \
         patch("os.remove") as mock_remove, \
         patch("os.path.exists", return_value=True), \
         patch("src.services.ingestion_service.update_daily_snapshot") as mock_update:
        
        mock_read_csv.return_value = "DataFrame"
        
        success, msg = service.process_csv_upload(mock_file, "robinhood")
        
        assert success is True
        assert "匯入成功" in msg
        mock_factory.get_ingestor.assert_called_with("robinhood", "test.db")
        mock_ingestor.ingest.assert_called_with("DataFrame", user_id="user1")
        mock_update.assert_called()
        mock_remove.assert_called()

def test_process_csv_upload_failure(service, mock_factory):
    mock_file = MagicMock()
    mock_factory.get_ingestor.side_effect = Exception("Format Error")
    
    with patch("builtins.open", new_callable=MagicMock), \
         patch("src.services.ingestion_service.pd.read_csv"), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:
        
        success, msg = service.process_csv_upload(mock_file, "simple")
        
        assert success is False
        assert "Format Error" in msg
        mock_remove.assert_called()
