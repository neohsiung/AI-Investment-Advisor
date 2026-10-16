"""
Phase 0 safety gates: synthetic-data evolution must be off by default and the
compositor must never score with LLM-generated code or random prices unless
explicitly enabled.
Phase 0 安全閘：合成資料演化預設關閉；未明確開啟前，評分絕不執行 LLM 生成程式碼，
也不以隨機價格代算。
"""
import asyncio
from unittest.mock import MagicMock, patch

import yaml


def _schema_default(key):
    with open("config/settings_schema.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    entries = data["settings"] if isinstance(data, dict) and "settings" in data else data
    for e in entries:
        if e.get("key") == key:
            return e.get("default")
    raise AssertionError(f"{key} missing from settings_schema.yaml")


def test_schema_defaults_are_off():
    assert _schema_default("auto_promote_synthesized_factors") is False
    assert _schema_default("allow_synthesized_factor_live_exec") is False
    assert _schema_default("enable_autonomous_evolution_beat") is False


def test_evolution_gate_fails_closed_on_read_error():
    from src.infrastructure import tasks

    with patch("src.services.settings_service.SettingsService", side_effect=RuntimeError("db down")):
        assert tasks._synthetic_evolution_enabled("u1") is False


def test_evolution_gate_respects_setting():
    from src.infrastructure import tasks

    svc = MagicMock()
    svc.get_setting.return_value = True
    with patch("src.services.settings_service.SettingsService", return_value=svc):
        assert tasks._synthetic_evolution_enabled("u1") is True
    svc.get_setting.return_value = "false"
    with patch("src.services.settings_service.SettingsService", return_value=svc):
        assert tasks._synthetic_evolution_enabled("u1") is False


def test_compositor_skips_exec_when_flag_off():
    from src.services.confidence_compositor_service import CompositorService

    svc = CompositorService(user_id="u1")
    art = MagicMock(source_code="raise SystemExit('must not run')", name="a")
    runner = MagicMock()
    runner.list_artifacts.return_value = [art]
    settings = MagicMock()
    settings.get_setting.return_value = False
    with patch("src.services.canary_shadow_runner.canary_runner", runner), \
         patch("src.services.settings_service.SettingsService", return_value=settings):
        out = asyncio.run(svc._gather_synthesized_factor_scores("NVDA"))
    assert out == []


def test_compositor_never_uses_random_prices():
    from src.services.confidence_compositor_service import CompositorService

    svc = CompositorService(user_id="u1")
    art = MagicMock(source_code="raise SystemExit('must not run')", name="a")
    runner = MagicMock()
    runner.list_artifacts.return_value = [art]
    settings = MagicMock()
    settings.get_setting.return_value = True
    mds = MagicMock()
    mds.get_history_df.return_value = None
    with patch("src.services.canary_shadow_runner.canary_runner", runner), \
         patch("src.services.settings_service.SettingsService", return_value=settings), \
         patch("src.services.market_data_service.MarketDataService", return_value=mds):
        out = asyncio.run(svc._gather_synthesized_factor_scores("NVDA"))
    assert out == []
