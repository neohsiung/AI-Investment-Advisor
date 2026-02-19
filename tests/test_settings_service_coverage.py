"""
Additional tests for Settings Service coverage.
測試 Settings Service 提高覆蓋率。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.settings_service import SettingsService

class TestSettingsService:
    
    def test_init(self):
        """Test service initialization."""
        service = SettingsService(db_path=":memory:", user_id="test_user")
        assert service.db_path == ":memory:"
        assert service.user_id == "test_user"
    
    @patch('src.services.settings_service.get_db_connection')
    def test_get_all_settings(self, mock_get_conn):
        """Test getting all settings for a user."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("key1", "value1"),
            ("key2", "value2")
        ]
        
        service = SettingsService(user_id="user123")
        result = service.get_all_settings()
        
        assert result == {"key1": "value1", "key2": "value2"}
        mock_conn.close.assert_called()
    
    @patch('src.services.settings_service.get_db_connection')
    def test_get_all_settings_empty_table(self, mock_get_conn):
        """Test getting settings when table doesn't exist."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("no such table")
        
        service = SettingsService(user_id="user123")
        result = service.get_all_settings()
        
        assert result == {}
    
    @patch('src.services.settings_service.get_db_connection')
    def test_get_setting(self, mock_get_conn):
        """Test getting a single setting."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("test_key", "test_value")
        ]
        
        service = SettingsService(user_id="user123")
        result = service.get_setting("test_key", default="default")
        
        assert result == "test_value"
    
    @patch('src.services.settings_service.get_db_connection')
    def test_get_setting_default(self, mock_get_conn):
        """Test getting a single setting with default value."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        
        service = SettingsService(user_id="user123")
        result = service.get_setting("missing_key", default="default_val")
        
        assert result == "default_val"
    
    @patch('src.services.settings_service.get_db_connection')
    def test_save_setting(self, mock_get_conn):
        """Test saving a setting."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        
        service = SettingsService(user_id="user123")
        success, msg = service.save_setting("key1", "new_value")
        
        assert success is True
        mock_conn.execute.assert_called()
        mock_conn.commit.assert_called()
    
    @patch('src.services.settings_service.get_db_connection')
    def test_save_setting_error(self, mock_get_conn):
        """Test error handling during save."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("DB Error")
        
        service = SettingsService(user_id="user123")
        success, msg = service.save_setting("key1", "value")
        
        assert success is False
        assert "DB Error" in msg
    
    @patch('src.services.settings_service.get_db_connection')
    def test_save_settings_bulk(self, mock_get_conn):
        """Test saving multiple settings."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        
        service = SettingsService(user_id="user123")
        success, msg = service.save_settings_bulk({"k1": "v1", "k2": "v2"})
        
        assert success is True
        assert mock_conn.execute.call_count == 4
    
    @patch('src.services.settings_service.requests.get')
    def test_fetch_openrouter_models(self, mock_get):
        """Test fetching OpenRouter models."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [
                {"id": "model1"},
                {"id": "model2"}
            ]
        }
        
        service = SettingsService()
        result = service.fetch_openrouter_models()
        
        assert "model1" in result
        assert "model2" in result
    
    @patch('src.services.settings_service.requests.get')
    def test_fetch_openrouter_models_error(self, mock_get):
        """Test handling error when fetching models."""
        mock_get.side_effect = Exception("Network Error")
        
        service = SettingsService()
        result = service.fetch_openrouter_models()
        
        assert result == []
