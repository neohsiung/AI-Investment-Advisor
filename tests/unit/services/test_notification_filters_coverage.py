"""
Tests for NotificationFilters - InterestBasedFilter coverage.
補充 notification_filters.py 的測試覆蓋率。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.notification_filters import InterestBasedFilter, DEFAULT_ROUTING_SCHEMA


class TestDefaultRoutingSchema:
    """Test the DEFAULT_ROUTING_SCHEMA constant."""

    def test_default_routing_schema_has_telegram(self):
        assert "telegram" in DEFAULT_ROUTING_SCHEMA

    def test_default_routing_schema_has_email(self):
        assert "email" in DEFAULT_ROUTING_SCHEMA

    def test_default_routing_schema_has_line(self):
        assert "line" in DEFAULT_ROUTING_SCHEMA

    def test_telegram_has_default_chat_id(self):
        assert "default_chat_id" in DEFAULT_ROUTING_SCHEMA["telegram"]

    def test_email_has_default_to(self):
        assert "default_to" in DEFAULT_ROUTING_SCHEMA["email"]

    def test_line_has_default_user_id(self):
        assert "default_user_id" in DEFAULT_ROUTING_SCHEMA["line"]

    def test_telegram_has_categories(self):
        telegram = DEFAULT_ROUTING_SCHEMA["telegram"]
        for cat in ["report", "sentinel", "approval", "trading"]:
            assert cat in telegram

    def test_email_has_categories(self):
        email = DEFAULT_ROUTING_SCHEMA["email"]
        for cat in ["report", "sentinel", "approval", "trading"]:
            assert cat in email


class TestInterestBasedFilterInit:
    """Test InterestBasedFilter initialization."""

    def test_init_with_settings_service(self):
        mock_settings = MagicMock()
        f = InterestBasedFilter(settings_service=mock_settings)
        assert f.settings_service is mock_settings

    def test_init_with_none_settings_service(self):
        f = InterestBasedFilter(settings_service=None)
        assert f.settings_service is None


class TestInterestBasedFilterGetRouting:
    """Test _get_routing method."""

    def test_get_routing_no_settings_service(self):
        f = InterestBasedFilter(settings_service=None)
        result = f._get_routing()
        assert result == {}

    def test_get_routing_returns_dict(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {"telegram": {"default_chat_id": "123"}}
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f._get_routing()
        assert isinstance(result, dict)
        assert "telegram" in result

    def test_get_routing_returns_empty_on_non_dict(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "not_a_dict"
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f._get_routing()
        assert result == {}

    def test_get_routing_returns_empty_on_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = Exception("DB error")
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f._get_routing()
        assert result == {}


class TestInterestBasedFilterGetRecipientOverride:
    """Test get_recipient_override method."""

    def test_get_recipient_override_telegram_with_override(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "telegram": {
                "sentinel": {"chat_id": "-100123456"}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("telegram", "sentinel")
        assert result == "-100123456"

    def test_get_recipient_override_email_with_override(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "email": {
                "report": {"to": "admin@example.com"}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("email", "report")
        assert result == "admin@example.com"

    def test_get_recipient_override_line_with_override(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "line": {
                "trading": {"user_id": "U123abc"}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("line", "trading")
        assert result == "U123abc"

    def test_get_recipient_override_returns_none_when_empty(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "telegram": {
                "sentinel": {"chat_id": ""}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("telegram", "sentinel")
        assert result is None

    def test_get_recipient_override_returns_none_when_missing(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {}
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("telegram", "sentinel")
        assert result is None

    def test_get_recipient_override_strips_whitespace(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "telegram": {
                "approval": {"chat_id": "  -100999  "}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("telegram", "approval")
        assert result == "-100999"

    def test_get_recipient_override_unknown_adapter_uses_chat_id(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = {
            "unknown": {
                "report": {"chat_id": "xyz"}
            }
        }
        f = InterestBasedFilter(settings_service=mock_settings)
        result = f.get_recipient_override("unknown", "report")
        assert result == "xyz"


class TestInterestBasedFilterShouldNotify:
    """Test should_notify method."""

    def test_should_notify_system_category_always_true(self):
        f = InterestBasedFilter(settings_service=None)
        mock_adapter = MagicMock()
        result = f.should_notify(mock_adapter, "system")
        assert result is True

    def test_should_notify_no_settings_service_returns_true(self):
        f = InterestBasedFilter(settings_service=None)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "TelegramAdapter"
        result = f.should_notify(mock_adapter, "report")
        assert result is True

    def test_should_notify_category_in_interests_returns_true(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "sentinel,report,approval"
        f = InterestBasedFilter(settings_service=mock_settings)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "TelegramAdapter"
        result = f.should_notify(mock_adapter, "report")
        assert result is True

    def test_should_notify_category_not_in_interests_returns_false(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "sentinel,approval"
        f = InterestBasedFilter(settings_service=mock_settings)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "EmailAdapter"
        result = f.should_notify(mock_adapter, "report")
        assert result is False

    def test_should_notify_case_insensitive(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "SENTINEL,REPORT"
        f = InterestBasedFilter(settings_service=mock_settings)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "TelegramAdapter"
        result = f.should_notify(mock_adapter, "sentinel")
        assert result is True

    def test_should_notify_adapter_type_resolution(self):
        """Test that adapter class name is correctly resolved to type."""
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "sentinel,report"
        f = InterestBasedFilter(settings_service=mock_settings)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "LineBotAdapter"
        # 'LineBotAdapter' -> 'line' (removes 'bot' and 'adapter')
        result = f.should_notify(mock_adapter, "sentinel")
        assert result is True

    def test_should_notify_trading_category(self):
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "sentinel,report,trading"
        f = InterestBasedFilter(settings_service=mock_settings)
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "SlackAdapter"
        result = f.should_notify(mock_adapter, "trading")
        assert result is True
