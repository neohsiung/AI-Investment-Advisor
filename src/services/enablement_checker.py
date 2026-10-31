"""G11 (L8): the enablement checker. When all six ADR-003 (6) conditions hold it switches charter_state from dry_run to
apply by itself; there is no operator click, and the operator's veto is the human stop.
G11（L8）：啟用檢查器。ADR-003 (6) 六個條件全部成立時，自動把 charter_state 由 dry_run 切到 apply；不需要操作者點擊，
操作者的否決手段是人工停止。

R3: this decides whether the change engine may write live values. It therefore fails closed:
  * a criterion that cannot be read is ``not_measurable`` and counts as NOT satisfied;
  * ``enable`` flips only ``mode == 'dry_run'`` with ``human_stop`` false, by a conditional UPDATE (exactly once), and
    never touches a frozen / human_stop / apply / tighten_only state;
  * ``drill`` always restores the previous state in a ``finally`` block and is never scheduled (operator endpoint only).
The six criteria: (1) ADR-003 is in mission.yaml; (2) dry_run ran >= 90 days counted from the EARLIEST verdict row in
charter_events (not charter_state.since, which a freeze/resume rewrites) and every adaptive parameter has a verdict;
(3) the zero-effect false-loosening rate, MEASURED here, is <= alpha; (4) a halt drill passed; (5) eight consecutive
weekly digests; (6) no K breach (a ``freeze`` event that is not a human stop) in the last 30 days.
Clock contract: every function takes ``now``; no SQL NOW(). Events are written through the injected ``emit`` (the task
shell binds charter_digest_service.notify_event), which also keeps this module free of an import cycle with the digest.
這是 R3 金錢路徑，故 fail-closed：讀不到的條件為 not_measurable 且視為未滿足；enable 只對 dry_run 且無 human_stop 做條件式
UPDATE（只切一次），絕不動 frozen／human_stop／apply／tighten_only；drill 一律在 finally 還原狀態、從不排程。
條件：(1) mission.yaml 有 ADR-003；(2) 自「最早的 verdict 列」起算 >= 90 天（不用會被 freeze／resume 改寫的 since）且每個 adaptive
參數至少一筆 verdict；(3) 零效應誤放寬率「實測」<= alpha；(4) 停機演練通過；(5) 連續 8 週週報；(6) 近 30 天無 K 違規。
"""
import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func, update
from sqlalchemy.orm import sessionmaker

from src.config.mission import load_mission
from src.config.parameter_registry import load_registry
from src.data.models import CharterEvent, CharterState
from src.evaluation.sequential import confidence_sequence_any_time_loosen, loosening_alpha
from src.services import charter_state_service
from src.services.charter_state_service import BLOCKING_MODES, read_state
from src.services.parameter_engine import n_cum

logger = logging.getLogger(__name__)

ADR_ID = "ADR-003"
DRY_RUN_MIN_DAYS = 90
DIGEST_WEEKS_REQUIRED = 8
FREEZE_LOOKBACK_DAYS = 30
SIM_RUNS = 2000                 # zero-effect paths / 零效應模擬路徑數
SIM_DAYS = 252                  # one trading year per path / 每條路徑一個交易年
SIM_SIGMA = 0.02
SIM_SEED = 20261019             # fixed, written into the evidence / 固定種子，寫入證據
# A real BUY producer and a real non-exit SELL producer, neither on the frozen whitelist.
# 真實的買單與非出場賣單產生端，都不在凍結白名單內。
DRILL_BUY_STRATEGY = "cash_deployment"
DRILL_SELL_STRATEGY = "rebalance_diversification"
DRILL_SAFE_STRATEGY = "stop_loss"
CRITERIA = ("adr", "dry_run_90d", "zero_effect_sim", "drill", "8_digests", "no_freeze_30d")
OK, NOT_OK, NOT_MEASURABLE = "ok", "not_ok", "not_measurable"

Emit = Callable[[str, Optional[str], Dict[str, Any]], None]
Result = Tuple[str, Dict[str, Any]]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _week_index(d: date) -> int:
    """Monday-based week number; equal for every day of one ISO week and +1 for the next. / 同一 ISO 週同值，下週 +1。"""
    return (d.toordinal() - 1) // 7


@lru_cache(maxsize=16)
def zero_effect_false_loosening_rate(alpha: float, n_runs: int = SIM_RUNS, n: int = SIM_DAYS,
                                     sigma: float = SIM_SIGMA, seed: int = SIM_SEED,
                                     claimed_sigma: Optional[float] = None) -> float:
    """Share of ``n_runs`` mu=0 return paths on which the any-time loosening bound ever exceeds 0 at level ``alpha``.
    ``claimed_sigma`` (default: the true sigma) is what the bound is told; a smaller value voids the guarantee, which
    the measurement then shows. Deterministic for a fixed seed. / 零效應路徑中放寬下界曾 > 0 的比例；固定種子下可重現。"""
    rng = np.random.default_rng(seed)
    used = sigma if claimed_sigma is None else claimed_sigma
    hits = sum(confidence_sequence_any_time_loosen(rng.normal(0.0, sigma, n), alpha, used) for _ in range(n_runs))
    return hits / n_runs


# ── the six criteria; each returns (status, evidence) ─────────────────────────────────────────────────────────────
def _c_adr(engine: Any, now: datetime) -> Result:
    ids = [a.id for a in load_mission().adr]
    return (OK if ADR_ID in ids else NOT_OK), {"required": ADR_ID, "found": ADR_ID in ids}


def _c_dry_run(engine: Any, now: datetime) -> Result:
    with sessionmaker(bind=engine)() as s:
        base = s.query(CharterEvent).filter(CharterEvent.kind == "verdict", CharterEvent.key.isnot(None))
        earliest = base.with_entities(func.min(CharterEvent.created_at)).scalar()
        keys = {k for (k,) in base.with_entities(CharterEvent.key).distinct()}
    days = (now - _aware(earliest)).days if earliest is not None else None
    missing = [p.key for p in load_registry().parameters if p.policy == "adaptive" and p.key not in keys]
    ok = days is not None and days >= DRY_RUN_MIN_DAYS and not missing
    return (OK if ok else NOT_OK), {"days": days, "required_days": DRY_RUN_MIN_DAYS, "keys_without_verdict": missing}


def _c_sim(engine: Any, now: datetime) -> Result:
    with sessionmaker(bind=engine)() as s:
        n = n_cum(s)
    alpha = loosening_alpha(n)
    rate = zero_effect_false_loosening_rate(alpha)
    return (OK if rate <= alpha else NOT_OK), {"rate": rate, "alpha": alpha, "n_cum": n, "runs": SIM_RUNS,
                                               "days": SIM_DAYS, "sigma": SIM_SIGMA, "seed": SIM_SEED}


def _c_drill(engine: Any, now: datetime) -> Result:
    with sessionmaker(bind=engine)() as s:
        payloads = [(r.payload_json or {}) for r in s.query(CharterEvent).filter(CharterEvent.kind == "drill")]
    passed = sum(1 for p in payloads if p.get("ok") is True)
    return (OK if passed else NOT_OK), {"drills": len(payloads), "passed": passed}


def _c_digests(engine: Any, now: datetime) -> Result:
    with sessionmaker(bind=engine)() as s:
        stamps = [_aware(r.created_at) for r in s.query(CharterEvent).filter(CharterEvent.kind == "digest")]
    weeks = sorted({_week_index(t.date()) for t in stamps if t <= now})
    run = 1 if weeks else 0
    for i in range(len(weeks) - 2, -1, -1):
        if weeks[i] != weeks[i + 1] - 1:
            break
        run += 1
    gap = _week_index(now.date()) - weeks[-1] if weeks else None
    ok = run >= DIGEST_WEEKS_REQUIRED and gap is not None and gap <= 1       # the run must reach this or last week
    return (OK if ok else NOT_OK), {"consecutive_weeks": run, "required": DIGEST_WEEKS_REQUIRED,
                                    "weeks_since_latest": gap}


def _c_freeze(engine: Any, now: datetime) -> Result:
    since = now - timedelta(days=FREEZE_LOOKBACK_DAYS)
    with sessionmaker(bind=engine)() as s:
        rows = s.query(CharterEvent).filter(CharterEvent.kind == "freeze", CharterEvent.created_at >= since).all()
        breaches = [r for r in rows if _aware(r.created_at) <= now and (r.payload_json or {}).get("source") != "human"]
    return (NOT_OK if breaches else OK), {"freezes": len(breaches), "lookback_days": FREEZE_LOOKBACK_DAYS}


_CHECKS = (("adr", _c_adr), ("dry_run_90d", _c_dry_run), ("zero_effect_sim", _c_sim), ("drill", _c_drill),
           ("8_digests", _c_digests), ("no_freeze_30d", _c_freeze))


def check(engine: Any, now: datetime) -> Tuple[bool, List[Dict[str, Any]]]:
    """(all six hold, the criteria that do not). A criterion that cannot be evaluated is ``not_measurable`` and counts
    as not satisfied. Each missing item is {'criterion', 'status', 'value'}. / 讀不到的條件為 not_measurable，視為未滿足。"""
    missing: List[Dict[str, Any]] = []
    for name, fn in _CHECKS:
        try:
            status, value = fn(engine, now)
        except Exception as e:
            logger.warning("enablement criterion %s not measurable: %s", name, e)
            status, value = NOT_MEASURABLE, {"error": f"{type(e).__name__}: {e}"}
        if status != OK:
            missing.append({"criterion": name, "status": status, "value": value})
    return not missing, missing


def _emit(emit: Optional[Emit], kind: str, payload: Dict[str, Any]) -> None:
    """The state change is already committed; a failed notice is logged loudly, never allowed to undo it."""
    if emit is None:
        return
    try:
        emit(kind, None, payload)
    except Exception as e:
        logger.error("charter %s recorded in charter_state but event/notice failed: %s", kind, e)


def enable(engine: Any, now: datetime, emit: Optional[Emit] = None) -> Dict[str, Any]:
    """Switch dry_run -> apply once, only if all six criteria hold, mode is 'dry_run' and there is no human stop.
    The flip is a conditional UPDATE (where mode='dry_run' and human_stop is false), so a concurrent stop or freeze
    wins and nothing is emitted. An unreadable state means not enabled. / 條件式 UPDATE，只切一次；讀不到狀態即不啟用。"""
    try:
        st = read_state(engine)
    except Exception as e:
        logger.warning("enablement: charter_state unreadable, not enabling (fail closed): %s", e)
        return {"enabled": False, "missing": [], "reason": f"charter_state unreadable: {type(e).__name__}"}
    if st.mode != "dry_run" or st.human_stop:
        return {"enabled": False, "missing": [], "reason": f"mode {st.mode}, human_stop {st.human_stop}"}
    ok, missing = check(engine, now)
    if not ok:
        return {"enabled": False, "missing": missing, "reason": "criteria missing"}
    reason = "enablement: all six ADR-003 (6) criteria hold"
    with sessionmaker(bind=engine)() as s:
        n = s.execute(update(CharterState).where(
            CharterState.id == 1, CharterState.mode == "dry_run", CharterState.human_stop.is_(False)
        ).values(mode="apply", reason=reason, since=now, updated_at=now)).rowcount
        s.commit()
    if not n:
        return {"enabled": False, "missing": [], "reason": "state changed concurrently"}
    _emit(emit, "enable", {"from": "dry_run", "to": "apply", "reason": reason})
    return {"enabled": True, "missing": [], "reason": reason}


def drill(engine: Any, now: datetime, emit: Optional[Emit] = None) -> Dict[str, Any]:
    """Halt drill: set frozen, check that a non-safety BUY is refused and a stop_loss SELL is allowed by the real gate,
    restore the previous state in ``finally`` and record a 'drill' event with ok true/false. Never scheduled. A state
    that is already frozen / human_stop is left untouched and the drill is recorded as failed. The freeze records the prior
    mode as ``resume_mode``, so if the process dies before ``finally`` runs, the next watchdog pass resumes to that mode
    instead of falling back to dry_run. / 凍結時一併記下原模式，程序中途死掉時，看門狗解除後回到原模式而非 dry_run。
    停機演練：設 frozen，確認非白名單買單與非出場賣單被擋、stop_loss 賣單放行，finally 還原原狀態並記一筆 drill 事件。
    從不排程。"""
    result: Dict[str, Any] = {"ok": False, "buy_refused": None, "nonexit_sell_refused": None,
                              "stop_loss_allowed": None, "error": None}
    try:
        prior = read_state(engine)
    except Exception as e:
        logger.warning("drill: charter_state unreadable: %s", e)
        result["error"] = f"charter_state unreadable: {type(e).__name__}"
        _emit(emit, "drill", result)
        return result
    if prior.mode in BLOCKING_MODES or prior.human_stop:
        result["error"] = f"state already {prior.mode}; drill not run"
        _emit(emit, "drill", result)
        return result
    try:
        with sessionmaker(bind=engine)() as s:
            n = s.execute(update(CharterState).where(
                CharterState.id == 1, CharterState.human_stop.is_(False), CharterState.mode.notin_(BLOCKING_MODES)
            ).values(mode="frozen", reason="drill", resume_mode=prior.mode, since=now, updated_at=now)).rowcount
            s.commit()
        if not n:
            raise RuntimeError("could not set frozen (state changed concurrently)")
        buy_ok, _ = charter_state_service.order_allowed("BUY", DRILL_BUY_STRATEGY, now, engine)
        nonexit_ok, _ = charter_state_service.order_allowed("SELL", DRILL_SELL_STRATEGY, now, engine)
        sell_ok, _ = charter_state_service.order_allowed("SELL", DRILL_SAFE_STRATEGY, now, engine)
        result["buy_refused"], result["nonexit_sell_refused"] = buy_ok is False, nonexit_ok is False
        result["stop_loss_allowed"] = sell_ok is True
    except Exception as e:
        logger.warning("drill failed: %s", e)
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        _restore(engine, now, prior, result)
    result["ok"] = (result["buy_refused"] is True and result["nonexit_sell_refused"] is True
                    and result["stop_loss_allowed"] is True and result["error"] is None)
    _emit(emit, "drill", result)
    return result


def _restore(engine: Any, now: datetime, prior: Any, result: Dict[str, Any]) -> None:
    """Put the pre-drill state back, only while the row is still the drill's own freeze (a human stop or watchdog
    freeze that landed meanwhile is not overwritten). A failure leaves the row frozen, the safe direction."""
    try:
        with sessionmaker(bind=engine)() as s:
            s.execute(update(CharterState).where(
                CharterState.id == 1, CharterState.mode == "frozen", CharterState.reason == "drill"
            ).values(mode=prior.mode, human_stop=prior.human_stop, reason=prior.reason, since=prior.since,
                     clears_on=prior.clears_on, breach_ids=list(prior.breach_ids) or None,
                     resume_mode=prior.resume_mode, updated_at=now))
            s.commit()
    except Exception as e:
        logger.error("drill: could not restore charter_state (left frozen, restore it by hand): %s", e)
        result["error"] = f"restore failed: {e}"
