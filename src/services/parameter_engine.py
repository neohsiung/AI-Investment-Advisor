"""
Charter change engine (G6) and its rollback / degrade loop (G9). The charter's only decider.
章程變更引擎（G6）與回滾／降級迴圈（G9）；章程唯一的決定者。

Once a day, for every ``policy: adaptive`` registry parameter: one tightening trigger (CUSUM or negative evidence on the
band a tightening would exclude) or five loosening conditions plus budgets (all computed by code from
marginal_band_evaluator series and sequential.py statistics) give a verdict loosen / tighten / hold.
  * Every verdict is recorded (parameter_changes row + charter_events 'verdict'), whatever the mode.
  * A value is written (param_policy.record_value, source='engine') only when charter_state allows it:
    loosen -> mode == 'apply'; tighten -> mode in apply / tighten_only / frozen; never while human_stop.
    In dry_run NOTHING is written to parameter_values or any live setting; trials are still registered.
  * An applied loosening is watched with CUSUM against its pre-change mean; an alarm restores the previous value
    (source='rollback') and starts a two-quarter cooldown for that key. 2 of the last 4 applied loosenings rolled
    back -> charter_state.mode = 'tighten_only'.
Failure rule: missing data = hold with a marked reason, never a plausible default; a DB failure raises (the task shell
logs WARNING and writes an error verdict event). Clock contract: every function takes ``now``; no SQL NOW().
每個 adaptive 參數每日判 loosen／tighten／hold；每筆判決一律記錄；只有 charter_state 允許才寫值；dry_run 不寫任何值。
缺資料＝hold 並標記原因；DB 失敗直接 raise；所有函式收 now，SQL 不用 NOW()。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from src.config.mission import load_mission
from src.config.parameter_registry import Parameter, load_registry
from src.data.models import (CharterEvent, CharterState, ParameterChange, ParameterTrial, StrategyTrial)
from src.evaluation.regime import RegimeCheck, regime_cell, regime_condition
from src.evaluation.sequential import (confidence_sequence_lower_bound, consecutive_window_check, cusum_alarm,
                                       loosening_alpha)
from src.services.marginal_band_evaluator import BandSeries, evaluate_key, sigma_upper
from src.services.param_policy import evidence_clock_start, get_param, record_value

logger = logging.getLogger(__name__)

IN_FLIGHT_DAYS = 91            # 63 trading days ~ 91 calendar days / 63 交易日約 91 日曆日
ROLLBACK_COOLDOWN_DAYS = 182   # two quarters / 兩季
MONITOR_MIN_N = 10
SPY_DAYS = 600                 # closes fetched once per run: 252 for the cell + up to 60 weeks of history / 每次執行取一次
MAX_REGIME_WEEKS = 60
TIGHTEN_MODES = ("apply", "tighten_only", "frozen")
NOT_MEASURABLE = "not_measurable"

Notify = Callable[..., None]


@dataclass(frozen=True)
class Verdict:
    key: str
    current: Any
    challenger: Optional[Any]
    direction: str                          # 'loosen' | 'tighten' | 'hold'
    conditions: Dict[str, Any]              # each condition True / False / 'not_measurable' with its numbers
    reasons: Tuple[str, ...]
    applied: bool


@dataclass(frozen=True)
class _State:
    mode: str
    human_stop: bool
    marker: Optional[str] = None

    def may_apply(self, direction: str) -> bool:
        if self.human_stop or self.mode == "human_stop" or self.marker:
            return False
        return self.mode == "apply" if direction == "loosen" else self.mode in TIGHTEN_MODES


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _jsonable(v: Any) -> Any:
    """numpy / nan / inf -> plain JSON (nan and inf become None; JSON columns refuse them). / 轉成純 JSON。"""
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.floating, float, np.integer, int)):
        f = float(v)
        return f if math.isfinite(f) else None
    return v


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    return ts.replace(tzinfo=timezone.utc) if ts is not None and ts.tzinfo is None else ts


def quarter_start(now: datetime) -> datetime:
    return datetime(now.year, 3 * ((now.month - 1) // 3) + 1, 1, tzinfo=timezone.utc)


def add_event(session: Session, user_id: str, kind: str, key: Optional[str], payload: Dict[str, Any],
              now: datetime) -> None:
    session.add(CharterEvent(user_id=user_id, kind=kind, key=key, payload_json=_jsonable(payload), created_at=now))


def record_event(engine: Any, user_id: str, kind: str, key: Optional[str], payload: Dict[str, Any],
                 now: datetime) -> None:
    """Stand-alone event write (task shell error path). Raises on failure. / 單獨寫一筆事件。"""
    with sessionmaker(bind=engine)() as s:
        add_event(s, user_id, kind, key, payload, now)
        s.commit()


def _read_state(engine: Any) -> _State:
    with sessionmaker(bind=engine)() as s:
        row = s.query(CharterState).filter(CharterState.id == 1).first()
        if row is None:       # no state row: record only, mark it. / 無狀態列：只記錄並標記。
            return _State("dry_run", False, "charter_state_missing")
        return _State(row.mode, bool(row.human_stop))


# ── grid, trials ─────────────────────────────────────────────────────────────────────────────────────────────────
def grid_neighbours(p: Parameter, current: float) -> Tuple[Optional[float], Optional[float]]:
    """(one step looser, one step tighter). ``current`` off the grid raises ValueError (the engine holds and marks).
    (放寬一格, 收緊一格)；current 不在 grid 上 → ValueError。"""
    grid = [float(g) for g in p.grid]
    i = grid.index(float(current))
    step = 1 if p.risk_direction > 0 else -1

    def pick(j: int) -> Optional[float]:
        return grid[j] if 0 <= j < len(grid) else None
    return pick(i + step), pick(i - step)


def n_cum(session: Session) -> int:
    """Cumulative trial count N for the multiple-testing correction: parameter trials + lab strategy trials (ADR-003).
    多重檢定的累計試驗數：參數試驗加實驗室策略試驗。"""
    return int(session.query(func.count(ParameterTrial.id)).scalar() or 0) + \
        int(session.query(func.count(StrategyTrial.params_hash)).scalar() or 0)


def register_trial(session: Session, key: str, grid_value: float, now: datetime) -> bool:
    """Idempotent on (key, grid_value): re-evaluating the same challenger is not a new trial. True if newly added.
    以 (key, grid_value) 冪等：重複評估同一挑戰值不多算一次試驗。"""
    known = [float(t.grid_value) for t in session.query(ParameterTrial).filter(ParameterTrial.key == key)]
    if float(grid_value) in known:
        return False
    session.add(ParameterTrial(key=key, grid_value=float(grid_value), n_cum=n_cum(session) + 1, registered_at=now))
    session.flush()
    return True


# ── the decision rules ───────────────────────────────────────────────────────────────────────────────────────────
def loosening_conditions(series: Dict[Tuple[int, float], BandSeries], alpha: float, min_n: int,
                         regime: RegimeCheck) -> Dict[str, Any]:
    """The five loosening conditions at every (horizon, cost multiplier); ``all`` is True only if every one holds.
    五個放寬條件；全部成立 ``all`` 才為 True。"""
    c: Dict[str, Any] = {}
    for (h, m), s in series.items():
        if s.unavailable_reason:
            return {"unavailable": s.unavailable_reason}
        cs = confidence_sequence_lower_bound(s.net_returns, alpha, sigma_upper(s.net_returns))
        c[f"cs_lower_gt0_{h}d_x{m}"] = bool(cs.loosen_ok)                           # condition 1 (incl. n >= MIN_SAMPLE)
        c[f"n_ge_min_{h}d_x{m}"] = bool(s.n >= min_n)                               # condition 4
        c[f"mean_{h}d_x{m}"] = float(np.mean(s.net_returns)) if s.n else float("nan")
        c[f"lower_{h}d_x{m}"] = float(cs.lower)
        if h == 63:
            c[f"w21x3_x{m}"] = bool(consecutive_window_check(s.daily_returns, 21, 3, 0.5).ok)     # condition 2
            c[f"w63x2_x{m}"] = bool(consecutive_window_check(s.daily_returns, 63, 2, None).ok)    # condition 3
    for m in {m for _, m in series}:
        a, b = c.get(f"mean_5d_x{m}", float("nan")), c.get(f"mean_63d_x{m}", float("nan"))
        c[f"same_sign_5_63_x{m}"] = bool(a > 0 and b > 0)                           # a NaN mean compares False
    c["regime"] = bool(regime.ok) if regime.measurable else NOT_MEASURABLE          # condition 5
    c["all"] = all(v is True for k, v in c.items() if k != "all" and not k.startswith(("mean_", "lower_")))
    return c


def tighten_trigger(series_63_x1: BandSeries) -> Tuple[bool, str]:
    """For the band a tightening would exclude: one-sided CUSUM alarm (baseline 0) or gate_policy-style negative
    evidence (n >= 10 and mean + se < 0). / 收緊會排除的區間：CUSUM 報警或負證據。"""
    x = series_63_x1.net_returns
    if x.size == 0:
        return False, "no_data"
    cu = cusum_alarm(x, baseline_mean=0.0, sigma=sigma_upper(x))
    if cu.alarm:
        return True, f"cusum_alarm@{cu.alarm_index}"
    if x.size >= 10 and (x.mean() + x.std(ddof=1) / np.sqrt(x.size)) < 0:
        return True, "negative_evidence_mean_plus_se"
    return False, "ok"


def _last_four_loosenings(session: Session) -> List[ParameterChange]:
    return (session.query(ParameterChange)
            .filter(ParameterChange.direction == "loosen", ParameterChange.applied_at.isnot(None))
            .order_by(ParameterChange.applied_at.desc(), ParameterChange.id.desc()).limit(4).all())


def budget_gate(session: Session, p: Parameter, now: datetime, engine: Any) -> Dict[str, bool]:
    """Six budget / cooldown checks (ADR-003); every one must be True before a loosening. / 六道預算與冷卻檢查。"""
    clock = evidence_clock_start(p.key, engine)
    applied = session.query(ParameterChange).filter(ParameterChange.direction == "loosen",
                                                    ParameterChange.applied_at.isnot(None))
    q0 = quarter_start(now)
    cap = load_mission().budgets.max_hypothesis_trials_per_quarter
    trials_q = session.query(func.count(ParameterTrial.id)).filter(ParameterTrial.registered_at >= q0).scalar() or 0
    strat_q = session.query(func.count(StrategyTrial.params_hash)).filter(StrategyTrial.first_eval_at >= q0).scalar() or 0
    rolled = session.query(func.count(ParameterChange.id)).filter(
        ParameterChange.key == p.key, ParameterChange.rolled_back_at.isnot(None),
        ParameterChange.rolled_back_at > now - timedelta(days=ROLLBACK_COOLDOWN_DAYS)).scalar() or 0
    last4 = _last_four_loosenings(session)
    return {
        "cooldown_ok": clock is None or (now - clock).days >= p.cooldown_days,
        "none_in_flight": applied.filter(ParameterChange.rolled_back_at.is_(None),
                                         ParameterChange.applied_at > now - timedelta(days=IN_FLIGHT_DAYS)).count() == 0,
        "quarter_quota_ok": applied.filter(ParameterChange.applied_at >= q0).count() == 0,
        "trial_budget_ok": int(trials_q) + int(strat_q) < cap,
        "no_rollback_cooldown": int(rolled) == 0,
        "engine_not_degraded": sum(r.rolled_back_at is not None for r in last4) < 2,
    }


# ── regime source ────────────────────────────────────────────────────────────────────────────────────────────────
class _RegimeSource:
    """SPY closes fetched once per run; any failure -> not measurable (WARNING), never a default regime."""

    def __init__(self, provider: Optional[Callable[..., Any]]):
        self._provider, self._closes, self._failed = provider, None, False

    def _get(self) -> Optional[List[float]]:
        if self._closes is None and not self._failed:
            try:
                if self._provider is None:
                    raise RuntimeError("no closes provider")
                self._closes = [float(x) for x in self._provider("SPY", days=SPY_DAYS)]
            except Exception as e:
                self._failed = True
                logger.warning("parameter_engine: SPY closes unavailable (%s); regime not measurable", e)
        return self._closes

    def check(self, s63: BandSeries, today: date) -> RegimeCheck:
        closes = self._get()
        daily = s63.daily_returns
        if closes is None or daily.size == 0:
            return RegimeCheck(False, False, {})
        n_weeks = min(MAX_REGIME_WEEKS, max(1, math.ceil(daily.size / 5)))
        weeks, decisions = [], []
        for w in range(n_weeks):
            start = today - timedelta(days=7 * (n_weeks - w))
            end = len(closes) - 5 * (n_weeks - 1 - w)
            weeks.append((start, regime_cell(closes[:end])))
            decisions += [start for j in range(w * 5, min(daily.size, w * 5 + 5)) if daily[j] != 0.0]
        return regime_condition(weeks, decisions)


# ── per-parameter evaluation ─────────────────────────────────────────────────────────────────────────────────────
def _write_verdict(engine: Any, user_id: str, key: str, direction: str, verdict: str, from_v: Any, to_v: Any,
                   stat: Optional[float], window: Dict[str, Any], reasons: Tuple[str, ...], now: datetime) -> int:
    """parameter_changes row (applied_at NULL) + charter_events 'verdict' in one commit; returns the change id."""
    with sessionmaker(bind=engine)() as s:
        ch = ParameterChange(key=key, from_value_json=from_v, to_value_json=to_v, direction=direction,
                             test_statistic=stat if stat is not None and math.isfinite(stat) else None,
                             window_series_json=_jsonable(window), verdict=verdict, applied_at=None, created_at=now)
        s.add(ch)
        s.flush()
        add_event(s, user_id, "verdict", key, {"verdict": verdict, "direction": direction, "from": from_v, "to": to_v,
                                               "reasons": list(reasons), "change_id": ch.id}, now)
        s.commit()
        return int(ch.id)


def _apply(engine: Any, user_id: str, key: str, change_id: int, direction: str, from_v: Any, to_v: Any,
           now: datetime, notify: Notify) -> None:
    """Write the engine value, stamp applied_at, log 'apply'. Raises on failure (never swallowed). / 失敗即 raise。"""
    record_value(key, to_v, "engine", engine=engine, now=now, change_id=change_id)
    with sessionmaker(bind=engine)() as s:
        s.query(ParameterChange).filter(ParameterChange.id == change_id).update({"applied_at": now})
        add_event(s, user_id, "apply", key, {"direction": direction, "from": from_v, "to": to_v,
                                             "change_id": change_id}, now)
        s.commit()
    notify("apply", key=key, direction=direction, from_value=from_v, to_value=to_v)


def _hold(engine, user_id, p, cur, challenger, reasons, now, conditions=None) -> Verdict:
    _write_verdict(engine, user_id, p.key, "loosen", "hold", cur, None, None, {"conditions": conditions or {}},
                   tuple(reasons), now)
    return Verdict(p.key, cur, challenger, "hold", dict(conditions or {}), tuple(reasons), False)


def _evaluate_param(engine: Any, user_id: str, p: Parameter, state: _State, now: datetime, notify: Notify,
                    regime: _RegimeSource) -> Verdict:
    got = get_param(p.key, engine=engine)
    if got.fallback_reason or got.value is None:
        return _hold(engine, user_id, p, got.value, None, [f"get_param:{got.fallback_reason or 'no_value'}"], now)
    cur = got.value
    try:
        loosen_c, tighten_c = grid_neighbours(p, cur)
    except ValueError as e:
        return _hold(engine, user_id, p, cur, None, [f"off_grid: {e}"], now)
    since = evidence_clock_start(p.key, engine)
    base = ("charter_state_missing",) if state.marker else ()

    if tighten_c is not None:                                   # tightening first: one trigger is enough
        s = evaluate_key(engine, user_id, p.key, cur, tighten_c, since)[(63, 1.0)]
        if s.unavailable_reason:
            fire, why = False, f"unavailable:{s.unavailable_reason}"
        else:
            fire, why = tighten_trigger(s)
        if fire:
            applied = state.may_apply("tighten")
            cid = _write_verdict(engine, user_id, p.key, "tighten", "tighten", cur, tighten_c, None,
                                 {"trigger": why, "n": s.n}, base + (why,), now)
            if applied:
                _apply(engine, user_id, p.key, cid, "tighten", cur, tighten_c, now, notify)
            return Verdict(p.key, cur, tighten_c, "tighten", {"trigger": why}, base + (why,), applied)

    if p.cls == "D":
        return _hold(engine, user_id, p, cur, None, list(base) + ["class_d_never_loosens"], now)
    if loosen_c is None:
        return _hold(engine, user_id, p, cur, None, list(base) + ["at_grid_edge"], now)

    with sessionmaker(bind=engine)() as s:                       # dry_run registers trials too (consumes quarter quota)
        register_trial(s, p.key, loosen_c, now)
        s.commit()
        alpha = loosening_alpha(n_cum(s))
    series = evaluate_key(engine, user_id, p.key, cur, loosen_c, since)
    s63 = series.get((63, 1.0))
    rc = regime.check(s63, now.date()) if s63 is not None and not s63.unavailable_reason else RegimeCheck(False, False, {})
    cond = loosening_conditions(series, alpha, p.evidence.min_n, rc)
    with sessionmaker(bind=engine)() as s:
        gate = budget_gate(s, p, now, engine)
    ok = cond.get("all") is True and all(gate.values())
    reasons = list(base)
    if "unavailable" in cond:
        reasons.append(f"unavailable:{cond['unavailable']}")
    else:
        reasons += [f"cond:{k}" for k, v in cond.items() if v is not True and not k.startswith(("mean_", "lower_", "all"))]
    reasons += [f"gate:{k}" for k, v in gate.items() if not v]
    conditions = {**cond, "gate": gate, "alpha": alpha}
    s5 = series.get((5, 1.0))
    window = {"conditions": cond, "gate": gate, "alpha": alpha,
              "pre_change_mean_5d": float(np.mean(s5.net_returns)) if s5 is not None and s5.n else None}
    applied = ok and state.may_apply("loosen")
    cid = _write_verdict(engine, user_id, p.key, "loosen", "loosen" if ok else "hold", cur, loosen_c,
                         cond.get("lower_63d_x1.0"), window, tuple(reasons), now)
    if applied:
        _apply(engine, user_id, p.key, cid, "loosen", cur, loosen_c, now, notify)
    return Verdict(p.key, cur, loosen_c, "loosen" if ok else "hold", conditions, tuple(reasons), applied)


# ── G9: rollback monitor and degrade ─────────────────────────────────────────────────────────────────────────────
def monitor_rollbacks(engine: Any, user_id: str, now: datetime, notify: Notify) -> int:
    """CUSUM (5-day net returns of the admitted band since the change, baseline = the pre-change mean) on every applied,
    not yet rolled back loosening; an alarm restores the previous value as source='rollback'. Returns rollbacks done.
    對每筆已套用且未回滾的放寬做 CUSUM 監控；報警即以 source='rollback' 還原舊值。"""
    with sessionmaker(bind=engine)() as s:
        pending = [(c.id, c.key, c.from_value_json, c.to_value_json, c.applied_at,
                    (c.window_series_json or {}).get("pre_change_mean_5d"))
                   for c in s.query(ParameterChange).filter(ParameterChange.direction == "loosen",
                                                            ParameterChange.applied_at.isnot(None),
                                                            ParameterChange.rolled_back_at.is_(None)).order_by(ParameterChange.id)]
    done = 0
    for cid, key, from_v, to_v, applied_at, base in pending:
        if base is None:
            logger.warning("monitor_rollbacks: change %s (%s) has no pre_change_mean_5d; cannot monitor, skipped", cid, key)
            continue
        s5 = evaluate_key(engine, user_id, key, from_v, to_v, _aware(applied_at))[(5, 1.0)]
        if s5.unavailable_reason or s5.n < MONITOR_MIN_N:
            continue
        cu = cusum_alarm(s5.net_returns, baseline_mean=float(base), sigma=sigma_upper(s5.net_returns))
        if not cu.alarm:
            continue
        record_value(key, from_v, "rollback", engine=engine, now=now, change_id=cid)
        with sessionmaker(bind=engine)() as s:
            s.query(ParameterChange).filter(ParameterChange.id == cid).update(
                {"rolled_back_at": now, "verdict": "rolled_back"})
            add_event(s, user_id, "rollback", key, {"from": to_v, "to": from_v, "change_id": cid,
                                                    "cusum_alarm_index": cu.alarm_index}, now)
            s.commit()
        notify("rollback", key=key, from_value=to_v, to_value=from_v)
        done += 1
    return done


def maybe_degrade(session: Session, now: datetime, notify: Notify, user_id: str = "") -> bool:
    """2 of the last 4 applied loosenings rolled back -> charter_state.mode = 'tighten_only'. The caller commits.
    最近 4 次放寬有 2 次回滾 → mode 降為 tighten_only（呼叫端 commit）。"""
    rolled = sum(r.rolled_back_at is not None for r in _last_four_loosenings(session))
    st = session.query(CharterState).filter(CharterState.id == 1).first()
    if rolled < 2 or st is None or st.mode in ("tighten_only", "frozen", "human_stop"):
        return False
    st.mode, st.since = "tighten_only", now
    st.reason = "engine degraded: 2 of last 4 loosenings rolled back"
    add_event(session, user_id, "degrade", None, {"reason": st.reason, "rolled_back": rolled}, now)
    notify("degrade", reason=st.reason)
    return True


# ── entry point ──────────────────────────────────────────────────────────────────────────────────────────────────
def run_once(user_id: str, engine: Any, now: datetime, notify: Optional[Notify] = None,
             closes_provider: Optional[Callable[..., Any]] = None) -> List[Verdict]:
    """One daily pass. ``closes_provider(ticker, days=)`` returns closes (SPY for the regime). DB errors raise.
    每日一次；closes_provider 提供 SPY 收盤；DB 錯誤直接 raise。"""
    notify = notify or (lambda *a, **k: None)
    monitor_rollbacks(engine, user_id, now, notify)               # first: a rolled-back key is then judged from its restored value
    with sessionmaker(bind=engine)() as s:
        if maybe_degrade(s, now, notify, user_id):
            s.commit()
    state = _read_state(engine)
    regime = _RegimeSource(closes_provider)
    return [_evaluate_param(engine, user_id, p, state, now, notify, regime)
            for p in load_registry().parameters if p.policy == "adaptive"]
