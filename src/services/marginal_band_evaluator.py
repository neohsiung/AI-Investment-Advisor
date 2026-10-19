"""
Marginal-band evaluator (G5, ADR-003): read-only.

Joins the G1/G1b observation tables with their settled counterfactual `decision_outcomes` rows and returns, for a
registry key and a challenger value, the net-of-cost return series of the decisions that the challenger would have
newly admitted (loosening) or newly excluded (tightening). Nothing is written; settling is done by the existing
outcome_reflection_service. Missing data is excluded and counted, never defaulted (AGENTS.md constraint #0).

邊際區間評估器（G5）：唯讀。把 G1/G1b 觀察表與已結算的反事實 decision_outcomes 相接，回傳「門檻改為挑戰值後
新納入／新排除的決策」扣成本後的報酬序列。不寫任何東西；結算由既有 outcome_reflection_service 負責。
缺資料就排除並計數，絕不補預設值。

Trading days are approximated by weekdays (np.is_busday has no US holidays); the 5-day horizon is calendar days.
交易日以工作日近似（不含美股假日）；5 日 horizon 為日曆日。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import text

from src.config.evaluation import load_evaluation
from src.evaluation.sequential import winsorise
from src.services.signed_alpha import direction_of_signal, signed_alpha

logger = logging.getLogger(__name__)

HORIZONS = (5, 63)
SIGMA_FLOOR = 0.02          # 2%: lower bound of the sub-Gaussian proxy / 次高斯代理下限
SIGMA_INFLATION = 1.25
BAND_SOURCES = {"batch_deploy_min_confidence": "threshold_band",
                "rotation_min_score_delta": "rotation_pair",
                "rotation_min_holding_days": "rotation_pair"}
NO_RECORDER = "no_recorder_for_key"


@dataclass(frozen=True)
class SettledDecision:
    obs_date: date
    score: float            # the quantity compared with the threshold / 與門檻比較的量
    threshold: float        # threshold in force when recorded / 記錄當時生效的門檻
    gross_pct: float        # direction-corrected gross return, % / 方向校正後毛報酬（%）
    friction_pct: Optional[float]   # rotation rows only; None = no friction data / 僅 rotation 列


@dataclass(frozen=True)
class BandSeries:
    key: str
    horizon: int
    current: float
    challenger: float
    cost_multiplier: float
    net_returns: np.ndarray     # one per decision, fraction (not %), sorted by obs_date / 小數、依日期排序
    daily_returns: np.ndarray   # weekday series, zero where nothing observed / 無觀察日補 0
    n: int
    excluded_missing_friction: int = 0
    unavailable_reason: Optional[str] = None


def in_marginal_band(current: float, challenger: float, score: float) -> bool:
    """Every owner passes on score >= threshold, so loosening admits [challenger, current) and tightening excludes
    [current, challenger): both are [lo, hi). / 放寬新納入 [challenger, current)，收緊新排除 [current, challenger)。"""
    lo, hi = min(current, challenger), max(current, challenger)
    return lo <= score < hi


def sigma_upper(net_returns: np.ndarray) -> float:
    """Upper estimate of the sub-Gaussian proxy: 1.25x winsorised sd, floored at 2%. / 次高斯代理的偏大估計。"""
    if net_returns.size < 2:
        return SIGMA_FLOOR
    return max(SIGMA_FLOOR, SIGMA_INFLATION * float(np.std(winsorise(net_returns), ddof=1)))


def daily_zero_filled(decisions: List[Tuple[date, float]]) -> np.ndarray:
    """Spread over weekdays; same-day rows averaged; weekend dates roll to the next weekday; empty days are 0.
    依工作日鋪開，同日取平均，週末日期順延到下個工作日，無觀察日為 0。"""
    if not decisions:
        return np.empty(0)
    rolled = [(np.busday_offset(np.datetime64(d), 0, roll="forward"), r) for d, r in decisions]
    d0, d1 = min(d for d, _ in rolled), max(d for d, _ in rolled)
    days = np.arange(d0, d1 + 1, dtype="datetime64[D]")
    days = days[np.is_busday(days)]
    idx = {d: i for i, d in enumerate(days)}
    sums, cnt = np.zeros(days.size), np.zeros(days.size)
    for d, r in rolled:
        sums[idx[d]] += r
        cnt[idx[d]] += 1
    return np.where(cnt > 0, sums / np.maximum(cnt, 1), 0.0)


def round_trip_cost_pct(multiplier: float) -> float:
    return 2.0 * load_evaluation().cost_bps_per_side / 100.0 * multiplier   # bps -> %, both sides


def net_series(key: str, current: float, challenger: float, horizon: int, multiplier: float,
               decisions: List[SettledDecision]) -> BandSeries:
    picked: List[Tuple[date, float]] = []
    excl = 0
    for d in decisions:
        if not in_marginal_band(current, challenger, d.score):
            continue
        if BAND_SOURCES[key] == "rotation_pair":
            if d.friction_pct is None:       # no default cost: exclude and count / 不補預設成本
                excl += 1
                continue
            net = d.gross_pct - d.friction_pct * multiplier
        else:
            net = d.gross_pct - round_trip_cost_pct(multiplier)
        picked.append((d.obs_date, net / 100.0))
    picked.sort(key=lambda p: p[0])
    arr = np.array([r for _, r in picked], dtype=float)
    return BandSeries(key, horizon, current, challenger, multiplier, arr, daily_zero_filled(picked), int(arr.size), excl)


def _to_date(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _since_date(since: Optional[datetime]) -> Optional[date]:
    return None if since is None else _to_date(since)


def _load_threshold_band(engine: Any, user_id: str, key: str, horizon: int,
                         since: Optional[date]) -> List[SettledDecision]:
    sql = """
        SELECT o.obs_date, o.score, o.threshold_value, d.alpha_pct, d.signal
        FROM threshold_band_observations o
        JOIN decision_outcomes d ON d.proposal_id = o.id AND d.is_counterfactual = TRUE
             AND d.source = 'threshold_band' AND d.horizon_days = :h AND d.resolved_at IS NOT NULL
        WHERE o.user_id = :uid AND o.threshold_key = :key AND o.score IS NOT NULL AND o.data_marker IS NULL
          AND d.alpha_pct IS NOT NULL AND o.obs_date >= :since
        ORDER BY o.obs_date, o.id"""
    params: Dict[str, Any] = {"uid": user_id, "key": key, "h": horizon, "since": since or date.min}
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [SettledDecision(_to_date(r["obs_date"]), float(r["score"]), float(r["threshold_value"]),
                            signed_alpha(float(r["alpha_pct"]), direction_of_signal(r["signal"])), None)
            for r in rows]


def _load_rotation(engine: Any, user_id: str, key: str, horizon: int,
                   since: Optional[date]) -> List[SettledDecision]:
    sql = """
        SELECT r.obs_date, r.score_delta, r.holding_age_days, r.min_score_delta, r.min_holding_days,
               r.friction_pct, r.decision, b.realized_return_pct AS buy_ret, s.realized_return_pct AS sell_ret
        FROM rotation_pair_observations r
        JOIN decision_outcomes b ON b.proposal_id = r.id AND b.is_counterfactual = TRUE
             AND b.source = 'rotation_pair' AND b.signal = 'BUY' AND b.ticker = r.buy_ticker
             AND b.horizon_days = :h AND b.resolved_at IS NOT NULL
        JOIN decision_outcomes s ON s.proposal_id = r.id AND s.is_counterfactual = TRUE
             AND s.source = 'rotation_pair' AND s.signal = 'SELL' AND s.ticker = r.sell_ticker
             AND s.horizon_days = :h AND s.resolved_at IS NOT NULL
        WHERE r.user_id = :uid AND r.data_marker IS NULL AND r.obs_date >= :since
        ORDER BY r.obs_date, r.id"""
    params: Dict[str, Any] = {"uid": user_id, "h": horizon, "since": since or date.min}
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    out: List[SettledDecision] = []
    for r in rows:
        if r["buy_ret"] is None or r["sell_ret"] is None or r["score_delta"] is None \
                or r["holding_age_days"] is None:
            continue
        delta, age = float(r["score_delta"]), float(r["holding_age_days"])
        min_delta, min_hold = float(r["min_score_delta"]), float(r["min_holding_days"])
        if key == "rotation_min_score_delta":
            if age < min_hold:          # the swap could not have happened / 換倉本就不會發生
                continue
            score, thr = delta, min_delta
        else:
            if delta < min_delta:
                continue
            score, thr = age, min_hold
        gross = float(r["buy_ret"]) - float(r["sell_ret"])   # same benchmark: equals the alpha difference
        fr = None if r["friction_pct"] is None else float(r["friction_pct"])
        out.append(SettledDecision(_to_date(r["obs_date"]), score, thr, gross, fr))
    return out


def evaluate_key(engine: Any, user_id: str, key: str, current: float, challenger: float,
                 since: Optional[datetime] = None) -> Dict[Tuple[int, float], BandSeries]:
    """{(horizon, cost_multiplier): BandSeries}. A key without a recorder yields unavailable_reason on every
    combination. A DB failure raises: the caller logs WARNING and holds; no fake series is returned.
    無記錄器的鍵每個組合都帶 unavailable_reason；DB 失敗直接 raise，不回假序列。"""
    multipliers = [float(m) for m in load_evaluation().cost_multipliers]
    result: Dict[Tuple[int, float], BandSeries] = {}
    source = BAND_SOURCES.get(key)
    if source is None:
        empty = np.empty(0)
        for h in HORIZONS:
            for m in multipliers:
                result[(h, m)] = BandSeries(key, h, current, challenger, m, empty, empty, 0, 0, NO_RECORDER)
        return result
    since_d = _since_date(since)
    for h in HORIZONS:
        decisions = (_load_threshold_band(engine, user_id, key, h, since_d) if source == "threshold_band"
                     else _load_rotation(engine, user_id, key, h, since_d))
        for m in multipliers:
            result[(h, m)] = net_series(key, current, challenger, h, m, decisions)
    return result
