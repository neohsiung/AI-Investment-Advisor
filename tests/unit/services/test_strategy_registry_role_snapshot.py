"""is_safety_control must equal membership of SAFETY_CONTROLS for every known name, also when the self-registering
macro hedge contract fails to load (the fallback set must still cover it). Contract lookup stays first.
is_safety_control 對所有已知名稱須等於 SAFETY_CONTROLS 成員資格；macro 避險 contract 載入失敗時備援仍須涵蓋。"""
import sys

import pytest

from src.domain import strategy_names as sn
from src.services.strategy_registry import StrategyRegistry


@pytest.fixture
def fresh_registry():
    saved = (dict(StrategyRegistry._strategies), StrategyRegistry._initialized)
    StrategyRegistry._strategies.clear()
    StrategyRegistry._initialized = False
    yield StrategyRegistry
    StrategyRegistry._strategies.clear()
    StrategyRegistry._strategies.update(saved[0])
    StrategyRegistry._initialized = saved[1]


def test_is_safety_control_equals_role_membership(fresh_registry):
    for name in sorted(sn.universe()):
        assert fresh_registry.is_safety_control(name) == (name in sn.SAFETY_CONTROLS), name


def test_snapshot_holds_when_macro_hedge_contract_fails_to_load(fresh_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "src.services.macro_hedging_service", None)  # import raises ImportError
    for name in sorted(sn.universe()):
        assert fresh_registry.is_safety_control(name) == (name in sn.SAFETY_CONTROLS), name


def test_registered_safety_contracts_are_exactly_the_registered_role(fresh_registry):
    fresh_registry._ensure_initialized()
    registered = {k for k, v in fresh_registry._strategies.items() if type(v).__name__ == "SafetyExitContract"}
    assert registered == set(sn.SAFETY_REGISTERED)
