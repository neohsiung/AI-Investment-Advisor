"""
Ratchet invariants: today's known violations are listed explicitly; NEW violations fail, and the list
may only shrink (a stale entry also fails, forcing cleanup).
棘輪式不變量：既有違規明列於下；新增違規會失敗，清單只能縮小（過期條目同樣失敗，強迫清理）。

Each list is a TODO tracked by the governance plan (section J). Do not extend a list to make a test pass —
fix the code or write an ADR in config/mission.yaml.
"""
from tests.invariants.helpers import (
    evolution_files_calling_set_setting,
    executor_call_sites,
    hardcoded_confidence_counts,
    order_call_files,
    unresolved_src_imports,
)

# 1. Every `from src.x import y` must resolve (a missing module + a swallowed ImportError once
#    made the staggered-order service "simulate" fills for weeks).
KNOWN_UNRESOLVED_IMPORTS = {
    ("src/agents/cio.py", "src.repositories.broker_account_repository"),
    ("src/agents/cio.py", "src.repositories.holdings_repository"),
    ("src/services/staggered_dip_buying_service.py", "src.infrastructure.broker_service"),
}


def test_src_imports_resolve():
    now = unresolved_src_imports()
    assert now - KNOWN_UNRESOLVED_IMPORTS == set(), f"NEW unresolved src imports: {sorted(now - KNOWN_UNRESOLVED_IMPORTS)}"
    assert KNOWN_UNRESOLVED_IMPORTS - now == set(), f"fixed — remove from baseline: {sorted(KNOWN_UNRESOLVED_IMPORTS - now)}"


# 2. Single order executor: only the execution service may place/close broker orders.
EXECUTOR = "src/services/automated_trading_service.py"
KNOWN_ORDER_CALLERS = {
    # Both are fenced by `hasattr(broker, "place_order")` (no real broker has it) and refuse to record
    # simulated fills; remove them when a real limit-order path goes through the executor.
    "src/services/cross_sector_harvest_rebalance_service.py": 1,
    "src/services/staggered_dip_buying_service.py": 3,
}


def test_only_executor_places_orders():
    now = {k: v for k, v in order_call_files().items() if k != EXECUTOR}
    assert now == KNOWN_ORDER_CALLERS, (
        "order-placing call sites changed. New callers are forbidden; removed callers must be deleted from "
        f"KNOWN_ORDER_CALLERS. now={now}"
    )


# 2b. Callers of the executor entry point (`evaluate_and_execute_trade`), measured by AST on 2026-10-17.
#     The count may only shrink (WP7 shrink order); a new caller or a stale entry fails.
#     執行器入口呼叫點基線（AST 實測）；只能縮小，新增或過期條目皆失敗。
KNOWN_EXECUTOR_CALLERS = {
    "src/agents/skills/evaluate_trade/impl.py": 1,
    "src/services/actionable_alert_service.py": 1,
    "src/services/automated_trading_service.py": 1,
    "src/services/batch_cash_deployment_service.py": 1,
    "src/services/confidence_rebalance_service.py": 1,
    "src/services/sentinel_service.py": 8,
    "src/services/socket_manager.py": 1,
    "src/services/workflow_service.py": 3,
}


def test_no_new_executor_call_sites():
    now = executor_call_sites()
    assert now == KNOWN_EXECUTOR_CALLERS, (
        "executor call sites changed. New callers are forbidden; removed callers must be deleted from "
        f"KNOWN_EXECUTOR_CALLERS. now={now}"
    )


# 3. No hardcoded decision scores in decision modules (a literal confidence 8.5 let a rebalance sell 11 holdings).
DECISION_SCORE_MODULES = [
    "src/services/confidence_rebalance_service.py",
    "src/services/automated_trading_service.py",
    "src/services/sentinel_service.py",
]
KNOWN_HARDCODED_CONFIDENCE = {
    # confidence_rebalance_service.py is clean since the 2026-10-16 rebalance lock (was 1).
    "src/services/sentinel_service.py": 3,
}


def test_no_new_hardcoded_confidence_scores():
    assert hardcoded_confidence_counts(DECISION_SCORE_MODULES) == KNOWN_HARDCODED_CONFIDENCE


# 4. Evolution/synthesis code must not write live settings directly (promotion goes through a proposal table).
KNOWN_EVOLUTION_SET_SETTING = {
    # factor_genetic_evolution_engine.py left this set in G3: it records parameter_proposals rows instead.
    # Writes live settings via `settings_repo.set(` (blind spot until WP2 widened the matcher).
    "src/services/strategy_auto_evolution_service.py",
}


def test_evolution_code_does_not_write_live_settings():
    assert evolution_files_calling_set_setting() == KNOWN_EVOLUTION_SET_SETTING


# 5. mission invariant: trading_disabled_when_capital_cap_is_zero (percentage cap of 0 must block all sizing).
def test_zero_percentage_cap_disables_trading():
    from unittest.mock import MagicMock

    from src.services.capital_policy import tradable_capital

    repo = MagicMock()
    repo.get.side_effect = lambda uid, key: {"tradable_capital_pct": 0, "tradable_capital_usd": 0}.get(key)
    assert tradable_capital("u1", 1700.0, repo) == 0.0


# 6. SlippageGuardService must be handed a SettingsService (get_setting), not a repository (only .get):
#    the mismatch made the guard crash on every order and never run (2026-10-16 audit).
def test_slippage_guard_gets_a_settings_service():
    from tests.invariants.helpers import REPO

    src = (REPO / "src/services/automated_trading_service.py").read_text(encoding="utf-8")
    assert "SlippageGuardService(user_id=user_id, settings_service=self.settings_repo)" not in src
