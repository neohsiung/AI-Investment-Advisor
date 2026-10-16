"""
Guard rails for portfolio rebalancing sells (mission invariants).
再平衡賣單護欄（使命不變量）。

Why: on 2026-09-28/29 ConfidenceRebalanceService sold 11 holdings in one run (every position not in the 8-name
target set, with a hardcoded confidence of 8.5) and the broker ended up almost entirely in cash. This module is
pure and deterministic: it decides which proposed sells may run. LLM output never reaches it.
原因：2026-09-28/29 該服務一次賣出 11 檔（凡不在 8 檔目標集合者全賣、信心分數寫死 8.5）。
本模組為純函式、決定性：決定哪些提議的賣單可執行。

Rules (limits come from config/mission.yaml via load_mission, never copied here):
  1. Unhealthy portfolio/market data            -> reject every sell (fail-closed).
  2. A sell with no real score                  -> rejected (no invented confidence).
  3. Sells need a replacement plan              -> total buys must cover >= REPLACEMENT_COVERAGE of the sells.
  4. Daily caps (count + % of NAV, including sells already executed today); weakest-scored sells go first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config.mission import load_mission

REPLACEMENT_COVERAGE = 0.8   # buys must fund at least 80% of the sold value


@dataclass
class GuardDecision:
    approved: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)   # each has "guard_reason"
    reasons: List[str] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)

    @property
    def aborted(self) -> bool:
        return bool(self.rejected) and not self.approved


def _reject(d: GuardDecision, sell: Dict[str, Any], reason: str) -> None:
    d.rejected.append({**sell, "guard_reason": reason})


def evaluate_sells(
    sells: List[Dict[str, Any]],
    buys: List[Dict[str, Any]],
    total_value: float,
    data_healthy: bool,
    sold_today_count: int = 0,
    sold_today_amount: float = 0.0,
    limits: Optional[Any] = None,
    min_trade_usd: float = 10.0,
) -> GuardDecision:
    inv = limits or load_mission().invariants
    d = GuardDecision(limits={
        "max_sells_per_day": inv.max_nonsafety_sells_per_day,
        "max_sell_pct_of_nav": inv.max_nonsafety_sell_pct_of_nav,
        "replacement_coverage": REPLACEMENT_COVERAGE,
    })
    if not sells:
        return d

    # 1. fail-closed on unhealthy data
    if not data_healthy or total_value <= 0:
        for s in sells:
            _reject(d, s, "data_unhealthy")
        d.reasons.append("portfolio/market data unhealthy — all sells blocked")
        return d

    # 2. real score required
    scored: List[Dict[str, Any]] = []
    for s in sells:
        conf = s.get("confidence")
        try:
            ok = conf is not None and float(conf) > 0.0
        except (TypeError, ValueError):
            ok = False
        if ok:
            scored.append(s)
        else:
            _reject(d, s, "no_score")
    if len(scored) != len(sells):
        d.reasons.append(f"{len(sells) - len(scored)} sell(s) have no real score")

    # 3. daily caps — weakest score first; an over-sized sell is TRIMMED to the remaining value cap
    #    (so a 60% position is unwound over several days instead of never, or all at once).
    #    每日上限——分數最低者優先；超額的賣單縮減為剩餘額度（部位分數日逐步退出，而非一次或永不）。
    def _score(s: Dict[str, Any]) -> float:
        c = float(s["confidence"])
        return c * 10.0 if c <= 1.0 else c

    count_left = max(0, inv.max_nonsafety_sells_per_day - sold_today_count)
    amount_left = max(0.0, total_value * inv.max_nonsafety_sell_pct_of_nav / 100.0 - sold_today_amount)
    order = {id(s): i for i, s in enumerate(scored)}
    capped_ok: List[Dict[str, Any]] = []
    for s in sorted(scored, key=_score):
        amt = abs(float(s.get("delta_amount", 0.0)))
        if count_left <= 0:
            _reject(d, s, "daily_sell_count_cap")
            continue
        if amt > amount_left:
            if amount_left >= min_trade_usd:
                ratio = amount_left / amt
                s = {**s, "delta_amount": -round(amount_left, 2),
                     "delta_weight": round(float(s.get("delta_weight", 0.0)) * ratio, 2),
                     "guard_trimmed": True}
                amt = amount_left
                order[id(s)] = order.get(id(s), len(order))
            else:
                _reject(d, s, "daily_sell_value_cap")
                continue
        capped_ok.append(s)
        count_left -= 1
        amount_left -= amt

    # 4. replacement plan — what is still going to be sold must be matched by buys
    sell_value = sum(abs(float(s.get("delta_amount", 0.0))) for s in capped_ok)
    buy_value = sum(abs(float(b.get("delta_amount", 0.0))) for b in buys)
    if capped_ok and buy_value < REPLACEMENT_COVERAGE * sell_value:
        for s in capped_ok:
            _reject(d, s, "no_replacement_plan")
        d.reasons.append(
            f"no replacement plan: buys ${buy_value:.2f} < {REPLACEMENT_COVERAGE:.0%} of sells ${sell_value:.2f}"
        )
        return d

    # keep the caller's original ordering (e.g. most negative delta first)
    # 保持呼叫端原本的排序
    d.approved = sorted(capped_ok, key=lambda x: scored_index(x, scored))
    capped = [r for r in d.rejected if r["guard_reason"].startswith("daily_")]
    trimmed = [a for a in d.approved if a.get("guard_trimmed")]
    if capped:
        d.reasons.append(f"{len(capped)} sell(s) deferred by daily caps")
    if trimmed:
        d.reasons.append(f"{len(trimmed)} sell(s) trimmed to the daily value cap")
    return d


def scored_index(item: Dict[str, Any], scored: List[Dict[str, Any]]) -> int:
    """Original position of a (possibly trimmed copy of a) sell. / 賣單在原清單中的位置。"""
    for i, s in enumerate(scored):
        if s.get("ticker") == item.get("ticker"):
            return i
    return len(scored)


def scale_buys_to_budget(buys: List[Dict[str, Any]], budget: float, min_trade_usd: float) -> List[Dict[str, Any]]:
    """Shrink buys proportionally so they never exceed the cash that is actually available.
    等比例縮減買單，確保不超過實際可用現金（賣單被護欄擋下後使用）。"""
    total = sum(float(b.get("delta_amount", 0.0)) for b in buys)
    if total <= 0 or budget <= 0:
        return []
    if total <= budget:
        return buys
    ratio = budget / total
    out = []
    for b in buys:
        amt = round(float(b["delta_amount"]) * ratio, 2)
        if amt >= min_trade_usd:
            out.append({**b, "delta_amount": amt, "delta_weight": round(float(b.get("delta_weight", 0.0)) * ratio, 2)})
    return out
