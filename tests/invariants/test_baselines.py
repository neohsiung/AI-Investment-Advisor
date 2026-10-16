"""
Ratchet invariants: today's known violations are listed explicitly; NEW violations fail, and the list
may only shrink (a stale entry also fails, forcing cleanup).
棘輪式不變量：既有違規明列於下；新增違規會失敗，清單只能縮小（過期條目同樣失敗，強迫清理）。

Each list is a TODO tracked by the governance plan (section J). Do not extend a list to make a test pass —
fix the code or write an ADR in config/mission.yaml.
"""
from tests.invariants.helpers import (
    evolution_files_calling_set_setting,
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
    ("src/services/trend_hysteresis_lockout_service.py", "src.utils.redis_client"),
}


def test_src_imports_resolve():
    now = unresolved_src_imports()
    assert now - KNOWN_UNRESOLVED_IMPORTS == set(), f"NEW unresolved src imports: {sorted(now - KNOWN_UNRESOLVED_IMPORTS)}"
    assert KNOWN_UNRESOLVED_IMPORTS - now == set(), f"fixed — remove from baseline: {sorted(KNOWN_UNRESOLVED_IMPORTS - now)}"


# 2. Single order executor: only the execution service may place/close broker orders.
EXECUTOR = "src/services/automated_trading_service.py"
KNOWN_ORDER_CALLERS = {
    "src/services/actionable_alert_service.py": 1,
    "src/services/cross_sector_harvest_rebalance_service.py": 1,
    "src/services/shadow_ledger_service.py": 2,
    "src/services/staggered_dip_buying_service.py": 3,
}


def test_only_executor_places_orders():
    now = {k: v for k, v in order_call_files().items() if k != EXECUTOR}
    assert now == KNOWN_ORDER_CALLERS, (
        "order-placing call sites changed. New callers are forbidden; removed callers must be deleted from "
        f"KNOWN_ORDER_CALLERS. now={now}"
    )


# 3. No hardcoded decision scores in decision modules (a literal confidence 8.5 let a rebalance sell 11 holdings).
DECISION_SCORE_MODULES = [
    "src/services/confidence_rebalance_service.py",
    "src/services/automated_trading_service.py",
    "src/services/sentinel_service.py",
]
KNOWN_HARDCODED_CONFIDENCE = {
    "src/services/confidence_rebalance_service.py": 1,
    "src/services/sentinel_service.py": 3,
}


def test_no_new_hardcoded_confidence_scores():
    assert hardcoded_confidence_counts(DECISION_SCORE_MODULES) == KNOWN_HARDCODED_CONFIDENCE


# 4. Evolution/synthesis code must not write live settings directly (promotion goes through a proposal table).
KNOWN_EVOLUTION_SET_SETTING = {"src/services/factor_genetic_evolution_engine.py"}


def test_evolution_code_does_not_write_live_settings():
    assert evolution_files_calling_set_setting() == KNOWN_EVOLUTION_SET_SETTING
