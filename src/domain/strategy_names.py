"""Single definition of the strategy names that decision code reasons about, and of the roles those names play.
決策程式所用策略名稱與其「角色」的單一定義。

Why this exists / 為什麼要有它
  The same idea ("this order is a safety exit", "this is a routine rebalance") used to be hand-copied into a
  dozen tuples across the services, with different matching rules (exact in some, substring in others), and the
  copies drifted: a legacy name nobody sends lived in three of them, ``position_exit`` was in some and not others.
  同一個概念被手抄成十幾份清單、比對方式不一，且已互相不一致。

Rules / 規則
  * Pure module: no imports, no I/O. A name is a plain ``str`` constant (not an Enum: ``(str, Enum)`` formats
    differently on Python 3.10 and 3.11 and these names are written to logs and ``transactions.raw_data``).
  * One matching rule: ``normalize`` (strip, lower-case, empty -> None) then exact membership. No substring tests.
  * Each role answers ONE question and is a frozen copy of one existing list, member for member. This module only
    moves where the lists live; changing a member is a behaviour change and a separate, reviewed PR.
  * ``tests/invariants/test_strategy_name_ssot.py`` keeps new copies from appearing elsewhere.
"""
from typing import FrozenSet, Optional

# ── names that producers send (src/ and services/, found by AST) / 產生端實際送出的名稱 ─────────────────────────
STOP_LOSS = "stop_loss"
TRAILING_STOP_LOSS = "trailing_stop_loss"
TRAILING_STOP = "trailing_stop"                  # no producer in src/ today; still named by exemption lists
TAKE_PROFIT = "take_profit"
POSITION_EXIT = "position_exit"
EMERGENCY_EXIT = "emergency_exit"
EMERGENCY_HEDGE = "emergency_hedge"              # ADR-005: the Sentinel SQQQ hedge BUY (producer lands with that PR)
CAPITAL_ROTATION = "capital_rotation"
CASH_DEPLOYMENT = "cash_deployment"
BENCHMARK_PARKING = "benchmark_parking"
REBALANCE_DIVERSIFICATION = "rebalance_diversification"
PORTFOLIO_REBALANCE = "portfolio_rebalance"
CONCENTRATION_REBALANCE = "concentration_rebalance"
STAGNATION_PRUNING = "stagnation_pruning"
PYRAMIDING_SCALE_IN = "pyramiding_scale_in"
TACTICAL_FACTOR_ROTATION = "tactical_factor_rotation"
VIX_PANIC_REBOUND = "vix_panic_rebound"
MACRO_VOLATILITY_HEDGE = "macro_volatility_hedge"
ROUTINE_REBALANCE = "routine_rebalance"          # conversation_router dry-run label / 對話路由的試算標籤
MA_CROSSOVER_10_30 = "ma_crossover_10_30"        # webhook demo strategy / webhook 示範策略
LIFECYCLE_ADMISSION = "lifecycle_admission"      # shadow-ledger admission label / 影子帳本入列標籤
PROPOSAL_EVENT = "proposal_event"                # proposal_shadow_service.STRATEGY_ID

ALL: FrozenSet[str] = frozenset({
    STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP, TAKE_PROFIT, POSITION_EXIT, EMERGENCY_EXIT, EMERGENCY_HEDGE,
    CAPITAL_ROTATION, CASH_DEPLOYMENT, BENCHMARK_PARKING, REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE,
    CONCENTRATION_REBALANCE, STAGNATION_PRUNING, PYRAMIDING_SCALE_IN, TACTICAL_FACTOR_ROTATION, VIX_PANIC_REBOUND,
    MACRO_VOLATILITY_HEDGE, ROUTINE_REBALANCE, MA_CROSSOVER_10_30, LIFECYCLE_ADMISSION, PROPOSAL_EVENT,
})

# Names no producer sends any more but that still sit inside exemption lists. They are listed so the lists can be
# reproduced exactly now and deleted deliberately later (P7); the invariant test fails if a producer starts using
# one. / 已無產生端、但仍留在豁免清單裡的舊名；先逐字保留，之後有意識地刪除。
EMERGENCY_LIQUIDATION = "emergency_liquidation"
CIRCUIT_BREAKER = "circuit_breaker"
ROUTINE_SELL = "routine_sell"
REBALANCE = "rebalance"
BATCH_CASH_DEPLOYMENT = "batch_cash_deployment"
AUTOMATED_TRADING = "automated_trading"
LEGACY: FrozenSet[str] = frozenset({
    EMERGENCY_LIQUIDATION, CIRCUIT_BREAKER, ROUTINE_SELL, REBALANCE, BATCH_CASH_DEPLOYMENT, AUTOMATED_TRADING,
})

# `proposal_validator.py` builds ``proposal_<source>`` for these sources. / 提案驗證器組出的 proposal_<來源>。
PROPOSAL_SOURCES = ("event", "strategy", "rotation", "parking", "manual", "safety")

# A ledger label for rows that have no strategy name. It is a marker, not a strategy: it is not in ALL.
# 沒有策略名的紀錄所用的標記值；它是標記，不是策略，所以不在 ALL。
UNNAMED_LEDGER_LABEL = "AutomatedTrading"

# ── roles: each one is a verbatim copy of one existing list ─────────────────────────────────────────────────────
# StrategyRegistry.is_safety_control fallback tuple (strategy_registry.py). The registered contracts are consulted
# first and are NOT replaced by this set. / is_safety_control 的備援清單；已註冊的 contract 仍優先查。
SAFETY_CONTROLS: FrozenSet[str] = frozenset({
    STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP, EMERGENCY_EXIT, POSITION_EXIT, TAKE_PROFIT,
    CAPITAL_ROTATION, REBALANCE_DIVERSIFICATION, CASH_DEPLOYMENT, STAGNATION_PRUNING,
    MACRO_VOLATILITY_HEDGE, BENCHMARK_PARKING,
})

# The names StrategyRegistry registers as SafetyExitContract in its init loop (macro_volatility_hedge registers
# itself with its own contract). / 註冊迴圈以 SafetyExitContract 註冊的名稱。
SAFETY_REGISTERED: FrozenSet[str] = SAFETY_CONTROLS - {MACRO_VOLATILITY_HEDGE}

# proposal_shadow_service.SAFETY_EXIT_NAMES: exits that may skip the replacement-plan rule. A different question from
# SAFETY_CONTROLS, so it is not merged with it. / 可略過「替代計畫」規則的出場，與 SAFETY_CONTROLS 是不同的問題。
REPLACEMENT_PLAN_EXEMPT: FrozenSet[str] = frozenset({
    STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP, EMERGENCY_EXIT, MACRO_VOLATILITY_HEDGE,
})

# automated_trading_service: skip the intraday-reversal cooldown. / 略過日內反向單冷卻。
CHURN_COOLDOWN_EXEMPT: FrozenSet[str] = frozenset({
    STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP, EMERGENCY_EXIT, EMERGENCY_LIQUIDATION, POSITION_EXIT,
})

# automated_trading_service: the stop-loss family that auto-executes before any approval check. / 停損家族，先於審批自動執行。
STOP_LOSS_FAMILY: FrozenSet[str] = frozenset({STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP})

# automated_trading_service: orders treated as "routine" by the inference hurdle gate. / 推論門檻閘門的例行單。
INFERENCE_ROUTINE: FrozenSet[str] = frozenset({REBALANCE, BATCH_CASH_DEPLOYMENT, TACTICAL_FACTOR_ROTATION, AUTOMATED_TRADING})

# automated_trading_service: BUYs whose size is not rescaled by the dynamic sizer. / 動態倉位縮放不處理的買單。
NO_DYNAMIC_SCALING: FrozenSet[str] = frozenset({
    CASH_DEPLOYMENT, REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE, CONCENTRATION_REBALANCE,
})

# automated_trading_service: scheduled / model-authorised flows that are auto-approved. / 排程或模型授權、自動放行的流程。
AUTO_EXEC_REBALANCE: FrozenSet[str] = frozenset({
    CASH_DEPLOYMENT, REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE, CONCENTRATION_REBALANCE, CAPITAL_ROTATION,
})

# risk_manager: rebalance batches that skip the daily-trade limit. / 略過單日次數限制的再平衡批次。
DAILY_LIMIT_REBALANCE: FrozenSet[str] = frozenset({
    REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE, CONCENTRATION_REBALANCE, TACTICAL_FACTOR_ROTATION,
})

# friction / trend (substring tests today, written out as the exact names they match): an emergency stop is never
# blocked. / 摩擦與遲滯服務目前用子字串比對，這裡寫成它們實際會命中的完整名稱：緊急停損永不被擋。
EMERGENCY_STOP_EXEMPT: FrozenSet[str] = frozenset({
    STOP_LOSS, TRAILING_STOP_LOSS, TRAILING_STOP, EMERGENCY_EXIT, EMERGENCY_LIQUIDATION, CIRCUIT_BREAKER,
})

# Unified risk gateway: "routine sells" that the trend hysteresis lock may block. / 趨勢鎖可擋的例行賣單。
HYSTERESIS_ROUTINE_SELL: FrozenSet[str] = frozenset({ROUTINE_REBALANCE, ROUTINE_SELL})


# friction / trend / gateway substring tests, written out as the exact names they match today over every name in
# ``universe()``. A name containing none of the old keywords is simply not a member. The snapshot test in
# tests/unit/domain/test_strategy_names.py recomputes the old substring rule and compares.
# 摩擦、遲滯、閘門目前的子字串比對，寫成它們對 universe() 內每個名稱實際會命中的完整名稱；快照測試會用舊規則重算比對。
# friction: any(k in strat for k in ("rebalance", "rotation", "churn", "routine"))
FRICTION_ROUTINE_REBALANCE: FrozenSet[str] = frozenset({
    CAPITAL_ROTATION, REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE, CONCENTRATION_REBALANCE,
    TACTICAL_FACTOR_ROTATION, ROUTINE_REBALANCE, REBALANCE, ROUTINE_SELL, "proposal_rotation",
})
# friction: "deploy" in strat   ("open" in strat matches no name today, so it has no role)
FRICTION_DEPLOY: FrozenSet[str] = frozenset({CASH_DEPLOYMENT, BATCH_CASH_DEPLOYMENT})
# trend: BUY deadband exemption, any(k in strat for k in ("deploy", "cash", "dip", "staggered", "rebalance",
# "rotation", "tier", "approval", "manual", "reporting", "pruning")); an EMPTY name is exempt too, in the caller.
TREND_DEADBAND_EXEMPT: FrozenSet[str] = frozenset({
    CASH_DEPLOYMENT, BATCH_CASH_DEPLOYMENT, CAPITAL_ROTATION, REBALANCE_DIVERSIFICATION, PORTFOLIO_REBALANCE,
    CONCENTRATION_REBALANCE, TACTICAL_FACTOR_ROTATION, ROUTINE_REBALANCE, REBALANCE, STAGNATION_PRUNING,
    "proposal_rotation", "proposal_manual",
})


def universe() -> FrozenSet[str]:
    """Every name a decision rule can meet: producer names, legacy names and the ``proposal_<source>`` names."""
    return ALL | LEGACY | frozenset(f"proposal_{src}" for src in PROPOSAL_SOURCES)


def normalize(raw: Optional[str]) -> Optional[str]:
    """strip + lower-case; empty or None -> None. The one place a strategy name is normalised. / 唯一的正規化處。"""
    name = str(raw).strip().lower() if raw is not None else ""
    return name or None


def has_role(raw: Optional[str], role: FrozenSet[str]) -> bool:
    """Exact membership after ``normalize``. An unknown or empty name is simply not a member (False)."""
    name = normalize(raw)
    return name is not None and name in role
