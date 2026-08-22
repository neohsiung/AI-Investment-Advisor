"""
Regression tests for RiskManager.check_constraints setting coercion.
測試 RiskManager 對 ai_trading_enabled 的型別容錯。

Context (2026-08-02): Setting.value is a JSON column, so ai_trading_enabled can
legitimately be stored as a JSON boolean (the Streamlit trading tab writes a
Python bool). RiskManager did `enabled.lower()` on the raw value, raising
AttributeError: 'bool' object has no attribute 'lower' on EVERY execute_order
call. Every other reader already coerced via str(); this was the sole outlier.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.infrastructure.risk_manager import RiskManager


@pytest.fixture
def manager():
    with patch('src.infrastructure.risk_manager.AlchemyTransactionRepository'), \
         patch('src.infrastructure.risk_manager.AlchemySettingsRepository'):
        yield RiskManager()


def _stub_settings(manager, overrides: dict):
    """Route _get_setting through a dict, preserving the default arg."""
    def fake(user_id, key, default=None):
        return overrides.get(key, default)
    manager._get_setting = fake


class TestAiTradingEnabledCoercion:

    @pytest.mark.parametrize("stored", [True, "true", "True", "1", 1])
    def test_truthy_values_allow_trading(self, manager, stored):
        """A JSON boolean True must behave exactly like the string 'true'."""
        _stub_settings(manager, {"ai_trading_enabled": stored, "ai_max_daily_trades": 999})
        manager._get_dynamic_thresholds = lambda uid: {"max_daily_trades": 999}
        manager._get_daily_trade_count = lambda uid, day: 0
        manager._is_circuit_breaker_triggered = lambda *a, **kw: False

        assert manager.check_constraints("u1") is True

    @pytest.mark.parametrize("stored", [False, "false", "False", "0", 0])
    def test_falsy_values_block_trading(self, manager, stored):
        """A JSON boolean False must block, not crash."""
        _stub_settings(manager, {"ai_trading_enabled": stored})

        assert manager.check_constraints("u1") is False

    def test_boolean_true_does_not_raise_attributeerror(self, manager):
        """The exact production crash: bool has no .lower()."""
        _stub_settings(manager, {"ai_trading_enabled": True, "ai_max_daily_trades": 999})
        manager._get_dynamic_thresholds = lambda uid: {"max_daily_trades": 999}
        manager._get_daily_trade_count = lambda uid, day: 0
        manager._is_circuit_breaker_triggered = lambda *a, **kw: False

        try:
            manager.check_constraints("u1")
        except AttributeError as exc:  # pragma: no cover - regression guard
            pytest.fail(f"check_constraints raised AttributeError on bool: {exc}")

    def test_missing_setting_defaults_to_enabled(self, manager):
        _stub_settings(manager, {"ai_max_daily_trades": 999})
        manager._get_dynamic_thresholds = lambda uid: {"max_daily_trades": 999}
        manager._get_daily_trade_count = lambda uid, day: 0
        manager._is_circuit_breaker_triggered = lambda *a, **kw: False

        assert manager.check_constraints("u1") is True
