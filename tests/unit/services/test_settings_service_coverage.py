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
    
    def test_get_all_settings(self):
        """Test getting all settings for a user."""
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = [("key1", "value1"), ("key2", "value2")]
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        result = service.get_all_settings()
        
        assert result == {"key1": "value1", "key2": "value2"}
        # v4.3.0: Only called once for target user_id (no SYSTEM fallback)
        assert mock_repo.get_all.call_count == 1
    
    def test_get_all_settings_empty_table(self):
        """Test getting settings when table doesn't exist."""
        mock_repo = MagicMock()
        mock_repo.get_all.side_effect = Exception("no such table")
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        result = service.get_all_settings()
        
        assert result == {}
    
    def test_get_setting(self):
        """Test getting a single setting."""
        mock_repo = MagicMock()
        mock_repo.get.return_value = "test_value"
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        result = service.get_setting("test_key", default="default")
        
        assert result == "test_value"
        # repo.get is called with user_id, key, and None as default
        mock_repo.get.assert_called_once_with("user123", "test_key", "default")
    
    def test_get_setting_default(self):
        """Test getting a single setting with default value."""
        mock_repo = MagicMock()
        mock_repo.get.return_value = "default_val"
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        result = service.get_setting("missing_key", default="default_val")
        
        assert result == "default_val"
    
    def test_save_setting(self):
        """Test saving a setting."""
        mock_repo = MagicMock()
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        success, msg = service.save_setting("key1", "new_value")
        
        assert success is True
        mock_repo.set.assert_called_once_with("user123", "key1", "new_value")
    
    def test_save_setting_error(self):
        """Test error handling during save."""
        mock_repo = MagicMock()
        mock_repo.set.side_effect = Exception("DB Error")
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        success, msg = service.save_setting("key1", "value")
        
        assert success is False
        assert "DB Error" in msg
    
    def test_save_settings_bulk(self):
        """Test saving multiple settings."""
        mock_repo = MagicMock()
        
        service = SettingsService(user_id="user123", settings_repo=mock_repo)
        success, msg = service.save_settings_bulk({"k1": "v1", "k2": "v2"})
        
        assert success is True
        assert mock_repo.set.call_count == 2
    
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
