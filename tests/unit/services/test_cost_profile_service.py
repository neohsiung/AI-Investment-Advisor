import pytest
from unittest.mock import MagicMock
from pathlib import Path

from src.services.cost_profile_service import CostProfileService, COST_PROFILES


def test_list_profiles():
    profiles = CostProfileService.list_profiles()
    assert len(profiles) == 3
    ids = [p["id"] for p in profiles]
    assert "frugal" in ids
    assert "balanced" in ids
    assert "aggressive" in ids


def test_get_current_profile_default():
    mock_settings = MagicMock()
    mock_settings.get_setting.return_value = None

    service = CostProfileService(user_id="user-1", settings_service=mock_settings)
    current = service.get_current_profile()
    assert current["id"] == "balanced"
    assert current["is_active"] is True


def test_get_current_profile_explicit():
    mock_settings = MagicMock()
    mock_settings.get_setting.return_value = "frugal"

    service = CostProfileService(user_id="user-1", settings_service=mock_settings)
    current = service.get_current_profile()
    assert current["id"] == "frugal"
    assert current["sentinel_tick_minute"] == "*/30"


def test_apply_profile_valid(tmp_path):
    mock_settings = MagicMock()
    service = CostProfileService(user_id="user-1", settings_service=mock_settings)

    env_file = tmp_path / ".env"
    env_file.write_text("SOME_VAR=123\nSENTINEL_TICK_CRON_MINUTE=\"*/15\"\n", encoding="utf-8")

    result = service.apply_profile("aggressive", env_file_path=str(env_file))
    assert result["id"] == "aggressive"
    assert result["sentinel_tick_minute"] == "*/5"

    mock_settings.save_settings_bulk.assert_called_once_with({
        "cost_profile": "aggressive",
        "sentinel_breaking_news_interval_min": 10,
        "sentinel_macro_interval_min": 30,
        "sentinel_deep_interval_min": 30,
    })

    env_content = env_file.read_text(encoding="utf-8")
    assert 'SENTINEL_TICK_CRON_MINUTE="*/5"' in env_content


def test_apply_profile_invalid():
    mock_settings = MagicMock()
    service = CostProfileService(user_id="user-1", settings_service=mock_settings)

    with pytest.raises(ValueError, match="Unknown cost profile"):
        service.apply_profile("nonexistent")
