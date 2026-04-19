import pytest
from unittest.mock import MagicMock
from src.services.notification_settings_manager import NotificationSettingsManager, NotificationChannel, ReportType

@pytest.fixture
def mock_settings_repo():
    return MagicMock()

def test_notif_manager_init(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    assert manager.user_id == "user-123"

def test_get_notification_channels_default(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.return_value = "email" # default behavior
    
    channels = manager.get_notification_channels()
    assert channels == ["email"]

def test_get_notification_channels_custom(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.return_value = "email, telegram, web"
    
    channels = manager.get_notification_channels()
    assert "email" in channels
    assert "telegram" in channels
    assert "web" in channels
    assert len(channels) == 3

def test_get_notification_channels_invalid_fallback(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.return_value = "invalid_channel, another_junk"
    
    channels = manager.get_notification_channels()
    # Should fallback to default if no valid channels found
    assert channels == manager.DEFAULT_CHANNELS

def test_set_notification_channels_success(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    result = manager.set_notification_channels(["email", "telegram"])
    
    assert result is True
    mock_settings_repo.set.assert_called_with("user-123", "notification_channels", "email,telegram")

def test_get_enabled_report_types(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.return_value = "daily, weekly"
    
    reports = manager.get_enabled_report_types()
    assert "daily" in reports
    assert "weekly" in reports

def test_get_report_schedule_daily(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.return_value = "10:00 UTC"
    
    schedule = manager.get_report_schedule("daily")
    assert schedule == "10:00 UTC"
    mock_settings_repo.get.assert_called_with("user-123", "report_schedule_daily", default=manager.DEFAULT_DAILY_SCHEDULE)

def test_set_report_schedule(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    result = manager.set_report_schedule("weekly", "Friday 12:00 UTC")
    
    assert result is True
    mock_settings_repo.set.assert_called_with("user-123", "report_schedule_weekly", "Friday 12:00 UTC")

def test_get_notification_preferences(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.side_effect = ["email", "daily", "09:00 UTC", "Mon 09:00 UTC", "None"]
    
    prefs = manager.get_notification_preferences()
    assert prefs["notification_channels"] == ["email"]
    assert prefs["enabled_report_types"] == ["daily"]

def test_get_active_notification_channels_full_config(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    # 1. get_notification_channels -> "email,telegram,sms,webhook,web"
    # 2. telegram_chat_id -> "123456"
    # 3. notification_phone -> "+12345"
    # 4. notification_webhook_url -> "http://test.com"
    
    mock_settings_repo.get.side_effect = [
        "email,telegram,sms,webhook,web", # get_notification_channels
        "123456",                         # telegram_chat_id
        "+12345",                         # notification_phone
        "http://test.com"                # notification_webhook_url
    ]
    
    active = manager.get_active_notification_channels()
    assert "email" in active
    assert "telegram" in active
    assert "sms" in active
    assert "webhook" in active
    assert "web" in active

def test_get_active_notification_channels_missing_configs(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    # telegram selected but no chat_id
    mock_settings_repo.get.side_effect = [
        "email,telegram",  # get_notification_channels
        None               # telegram_chat_id
    ]
    
    active = manager.get_active_notification_channels()
    assert "email" in active
    assert "telegram" not in active

def test_exception_handling_graceful(mock_settings_repo):
    manager = NotificationSettingsManager(mock_settings_repo, "user-123")
    mock_settings_repo.get.side_effect = Exception("DB Down")
    
    channels = manager.get_notification_channels()
    assert channels == manager.DEFAULT_CHANNELS
