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

    def test_missing_setting_blocks_trading(self, manager):
        """
        An absent `ai_trading_enabled` must BLOCK, not permit.

        This test previously asserted the opposite — that a missing setting
        defaulted to enabled — which meant a fresh or partially-seeded database
        authorised live order placement with no row ever having been written.
        The schema default is false, so the gate now fails closed.

        原本斷言「缺少設定即視為啟用」：全新或只部分初始化的資料庫會在沒有任何
        設定列的情況下授權真實下單。schema 預設為 false，此閘門改為 fail-closed。
        """
        _stub_settings(manager, {"ai_max_daily_trades": 999})
        manager._get_dynamic_thresholds = lambda uid: {"max_daily_trades": 999}
        manager._get_daily_trade_count = lambda uid, day: 0
        manager._is_circuit_breaker_triggered = lambda *a, **kw: False

        assert manager.check_constraints("u1") is False

    def test_explicit_true_still_allows_trading(self, manager):
        """The fail-closed default must not break the configured-on case."""
        _stub_settings(manager, {"ai_trading_enabled": "true", "ai_max_daily_trades": 999})
        manager._get_dynamic_thresholds = lambda uid: {"max_daily_trades": 999}
        manager._get_daily_trade_count = lambda uid, day: 0
        manager._is_circuit_breaker_triggered = lambda *a, **kw: False

        assert manager.check_constraints("u1") is True
