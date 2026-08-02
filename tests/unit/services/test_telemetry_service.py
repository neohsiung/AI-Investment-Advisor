"""
Unit tests for TelemetryService (Loop 3, B-P3.2): opt-in-gated, no-op
unless the user has explicitly enabled telemetry.
"""
from unittest.mock import MagicMock, patch

from src.services.telemetry_service import TelemetryService


class TestIsEnabled:
    def test_disabled_by_default(self):
        svc = TelemetryService(user_id="u1")
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = False
        with patch("src.services.settings_service.SettingsService", return_value=mock_settings):
            assert svc.is_enabled() is False

    def test_enabled_when_setting_true(self):
        svc = TelemetryService(user_id="u1")
        mock_settings = MagicMock()
        mock_settings.get_setting.return_value = "true"
        with patch("src.services.settings_service.SettingsService", return_value=mock_settings):
            assert svc.is_enabled() is True

    def test_settings_failure_defaults_disabled(self):
        svc = TelemetryService(user_id="u1")
        with patch("src.services.settings_service.SettingsService", side_effect=Exception("db down")):
            assert svc.is_enabled() is False


class TestTrack:
    def test_noop_when_disabled_no_db_call(self):
        svc = TelemetryService(user_id="u1")
        with patch.object(svc, "is_enabled", return_value=False), \
             patch("src.data.database.get_db_engine") as mock_engine:
            svc.track("viewed_backtest_page")
        mock_engine.assert_not_called()

    def test_writes_row_when_enabled(self):
        svc = TelemetryService(user_id="u1")
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn

        with patch.object(svc, "is_enabled", return_value=True), \
             patch("src.data.database.get_db_engine", return_value=engine):
            svc.track("viewed_backtest_page", {"page": "backtest"})

        params = conn.execute.call_args[0][1]
        assert params["uid"] == "u1"
        assert params["event"] == "viewed_backtest_page"

    def test_track_swallows_db_errors(self):
        svc = TelemetryService(user_id="u1")
        with patch.object(svc, "is_enabled", return_value=True), \
             patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            svc.track("some_event")  # must not raise
