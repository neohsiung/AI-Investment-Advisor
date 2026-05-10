import pytest
from unittest.mock import MagicMock
from src.services.notification_settings_manager import NotificationSettingsManager, NotificationChannel, ReportType

@pytest.fixture
def mock_settings_repo():
    return MagicMock()

def test_get_notification_channels_default(mock_settings_repo):
    user_id = "test_user"
    mock_settings_repo.get.return_value = "email" # default behavior
    
    manager = NotificationSettingsManager(mock_settings_repo, user_id)
    channels = manager.get_notification_channels()
    
    assert channels == ["email"]
    mock_settings_repo.get.assert_called_with(user_id, "notification_channels", default="email")

def test_get_notification_channels_custom(mock_settings_repo):
    user_id = "test_user"
    mock_settings_repo.get.return_value = "email, telegram, web"
    
    manager = NotificationSettingsManager(mock_settings_repo, user_id)
    channels = manager.get_notification_channels()
    
    assert "email" in channels
    assert "telegram" in channels
    assert "web" in channels
    assert len(channels) == 3

def test_get_active_notification_channels_telegram_missing_id(mock_settings_repo):
    user_id = "test_user"
    # User enabled email and telegram
    mock_settings_repo.get.side_effect = [
        "email,telegram", # for get_notification_channels
        None,             # for channel_telegram_chat_id (v10.0 priority check)
        None              # for telegram_chat_id (legacy fallback)
    ]
    
    manager = NotificationSettingsManager(mock_settings_repo, user_id)
    active = manager.get_active_notification_channels()
    
    assert "email" in active
    assert "telegram" not in active # Should be filtered out because no chat_id

def test_get_active_notification_channels_telegram_with_id(mock_settings_repo):
    user_id = "test_user"
    mock_settings_repo.get.side_effect = [
        "email,telegram", # for get_notification_channels
        "12345678"        # for telegram_chat_id check
    ]
    
    manager = NotificationSettingsManager(mock_settings_repo, user_id)
    active = manager.get_active_notification_channels()
    
    assert "email" in active
    assert "telegram" in active

def test_should_send_report(mock_settings_repo):
    user_id = "test_user"
    mock_settings_repo.get.return_value = "daily,weekly"
    
    manager = NotificationSettingsManager(mock_settings_repo, user_id)
    
    assert manager.should_send_report("daily") is True
    assert manager.should_send_report("monthly") is False
