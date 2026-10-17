"""
Pure trade-proposal validator (WP4) — NOT WIRED: nothing outside tests calls it yet.
純函式交易提案驗證器（WP4）——尚未接線，目前只有測試會呼叫。

An LLM may only PROPOSE (ticker / direction / rationale). Everything numeric — score, size, strategy name —
is decided here from injected, deterministic inputs. No DB, network, broker or LLM imports: every input arrives
through `ValidationContext`, so the function is trivially testable and cannot place an order.
LLM 只能「提案」；分數、金額、策略名稱全部由本函式依注入的決定性輸入決定。不得 import 任何
DB／網路／券商／LLM 模組。

Check order (first failure wins, each with a stable machine reason):
  1 schema  2 capital  3 deterministic score  4 sell replacement plan  5 buy sizing  6 risk gateway (fail closed)
Mission numbers are read from `ctx.mission` only — never copied here.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from src.services.rebalance_guard import evaluate_sells, scale_buys_to_budget

logger = logging.getLogger(__name__)

SCORE_MIN = 0.0
SCORE_MAX = 10.0
MIN_ORDER_USD_DEFAULT = 10.0
PCT_DENOMINATOR = 100.0

DIRECTIONS = ("BUY", "SELL")
SOURCES = ("event", "strategy", "rotation", "parking", "manual", "safety")
RESERVED_SYMBOLS = frozenset({"CASH", "USD", "GLOBAL", "MARKET"})
# Keys an LLM must never supply (sizing and scoring are deterministic). / LLM 不得提供的鍵。
FORBIDDEN_LLM_KEYS = frozenset(
    {"quantity", "qty", "score", "confidence", "amount", "amount_usd", "size", "weight"}
)


@dataclass(frozen=True)
class ValidationResult:
    approved: bool
    reason: str
    amount_usd: Optional[float]
    strategy_name: str
    score: Optional[float]
    # Benchmark buys the validator planned to fund an unpaired sell; the executor must run them.
    # 為未配對賣單自動規劃的基準買單（執行端必須走停泊路徑）。
    planned_buys: Tuple[Dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.approved and not (_is_num(self.amount_usd) and _is_num(self.score)):
            raise ValueError("approved result requires numeric amount_usd and score")


@dataclass
class ValidationContext:
    tradable_capital_usd: Any
    usable_cash_usd: Any
    mission: Any
    held_positions: Dict[str, float]
    paired_buys: List[Dict[str, Any]]
    research_lookup: Callable[[str], Optional[Tuple[float, float]]]
    max_research_age_days: float
    gateway_check: Callable[..., Any]
    benchmark_parking_available: bool
    per_order_cap_usd: float
    safety_exit_names: FrozenSet[str]
    min_order_usd: float = MIN_ORDER_USD_DEFAULT
    # Optional inputs for the sell guard (all injected). / 賣單護欄的選配輸入。
    position_values_usd: Dict[str, float] = field(default_factory=dict)
    total_value_usd: Optional[float] = None
    sold_today_count: int = 0
    sold_today_amount: float = 0.0
    data_healthy: bool = True


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _contains_forbidden_key(o: Any) -> bool:
    if isinstance(o, dict):
        return any(
            (isinstance(k, str) and k.strip().lower() in FORBIDDEN_LLM_KEYS) or _contains_forbidden_key(v)
            for k, v in o.items()
        )
    if isinstance(o, (list, tuple)):
        return any(_contains_forbidden_key(v) for v in o)
    return False


def _reject(reason: str, source: Any = None, score: Optional[float] = None) -> ValidationResult:
    name = f"proposal_{source}" if source in SOURCES else "proposal_invalid"
    return ValidationResult(False, reason, None, name, score)


def _degraded(res: Any) -> Any:
    direct = getattr(res, "_degraded_guards", None)
    if direct:
        return direct
    details = getattr(res, "guard_details", None)
    if isinstance(details, dict):
        return details.get("_degraded_guards")
    return None


def validate(proposal: Dict[str, Any], ctx: ValidationContext) -> ValidationResult:
    # 1. schema
    if not isinstance(proposal, dict):
        return _reject("invalid_proposal")
    source = proposal.get("source")
    direction = proposal.get("direction")
    ticker_raw = proposal.get("ticker")
    if _contains_forbidden_key(proposal):
        return _reject("llm_supplied_size", source)
    if direction not in DIRECTIONS:
        return _reject("invalid_direction", source)
    if not isinstance(ticker_raw, str) or not ticker_raw.strip():
        return _reject("invalid_ticker", source)
    ticker = ticker_raw.strip().upper()
    if ticker in RESERVED_SYMBOLS:
        return _reject("reserved_symbol", source)
    if source not in SOURCES:
        return _reject("invalid_source")
    strategy_name = f"proposal_{source}"

    def rej(reason: str, score: Optional[float] = None) -> ValidationResult:
        return ValidationResult(False, reason, None, strategy_name, score)

    # 2. mission / capital
    tradable = ctx.tradable_capital_usd
    if not _is_num(tradable) or float(tradable) <= 0:
        return rej("capital_disabled")
    tradable = float(tradable)

    # 3. deterministic score (never from the LLM)
    try:
        looked = ctx.research_lookup(ticker)
    except Exception as exc:  # fail closed: a broken lookup is a missing score
        logger.warning("proposal_validator: research lookup failed for %s: %s", ticker, exc)
        return rej("missing_score")
    try:
        raw_score, age = looked  # (score_0_to_10, age_days)
    except (TypeError, ValueError):  # None or malformed shape -> no usable score
        return rej("missing_score")
    if not _is_num(age) or not _is_num(ctx.max_research_age_days) or not (float(age) <= float(ctx.max_research_age_days)):
        return rej("stale_score")
    if not _is_num(raw_score) or not (SCORE_MIN <= float(raw_score) <= SCORE_MAX):
        return rej("invalid_score")
    score = float(raw_score)

    weight_cap = tradable * float(ctx.mission.promotion.max_initial_live_weight_pct) / PCT_DENOMINATOR
    planned: Tuple[Dict[str, Any], ...] = ()

    if direction == "SELL":
        # 4. sells
        if not _is_num(ctx.held_positions.get(ticker)) or float(ctx.held_positions[ticker]) <= 0:
            return rej("not_held", score)
        amount = min(weight_cap, float(ctx.per_order_cap_usd))
        held_value = ctx.position_values_usd.get(ticker)
        if _is_num(held_value) and float(held_value) > 0:
            amount = min(amount, float(held_value))
        if not _is_num(amount) or amount < ctx.min_order_usd:
            return rej("below_min_order", score)
        is_safety_exit = source == "safety" and proposal.get("exit_name") in ctx.safety_exit_names
        if not is_safety_exit:
            sell = {"ticker": ticker, "confidence": score, "delta_amount": -amount, "delta_weight": 0.0}
            total = ctx.total_value_usd if _is_num(ctx.total_value_usd) else tradable
            kw = dict(total_value=float(total), data_healthy=bool(ctx.data_healthy),
                      sold_today_count=ctx.sold_today_count, sold_today_amount=ctx.sold_today_amount,
                      limits=ctx.mission.invariants, min_trade_usd=ctx.min_order_usd)
            decision = evaluate_sells([sell], list(ctx.paired_buys), **kw)
            if (not decision.approved and ctx.benchmark_parking_available
                    and decision.rejected and decision.rejected[0].get("guard_reason") == "no_replacement_plan"):
                bench = {"ticker": ctx.mission.objective.benchmark, "delta_amount": amount, "delta_weight": 0.0}
                decision = evaluate_sells([sell], list(ctx.paired_buys) + [bench], **kw)
                if decision.approved:
                    trimmed = abs(float(decision.approved[0]["delta_amount"]))
                    planned = ({**bench, "delta_amount": trimmed},)
            if not decision.approved:
                gr = decision.rejected[0].get("guard_reason", "unknown") if decision.rejected else "unknown"
                return rej(gr if gr == "no_replacement_plan" else f"sell_guard_{gr}", score)
            amount = abs(float(decision.approved[0]["delta_amount"]))
    else:
        # 5. buy sizing
        want = min(weight_cap, float(ctx.per_order_cap_usd))
        cash = ctx.usable_cash_usd
        if not _is_num(cash) or float(cash) <= 0:
            return rej("below_min_order", score)
        sized = scale_buys_to_budget([{"ticker": ticker, "delta_amount": want, "delta_weight": 0.0}],
                                     float(cash), float(ctx.min_order_usd))
        amount = min(want, float(cash)) if sized else 0.0
        if not sized or amount < ctx.min_order_usd:
            return rej("below_min_order", score)

    # 6. risk gateway — fail closed
    try:
        res = ctx.gateway_check(ticker, direction, amount, strategy_name, score)
    except Exception as exc:
        logger.warning("proposal_validator: gateway check raised for %s %s: %s", direction, ticker, exc)
        return rej("gateway_error", score)
    if not getattr(res, "allowed", False):
        return rej("gateway_blocked", score)
    if _degraded(res):
        return rej("gateway_degraded", score)

    return ValidationResult(True, "approved", float(amount), strategy_name, score, planned)
