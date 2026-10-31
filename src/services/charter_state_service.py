"""G7: the charter halt. A K1/K3/K4 watchdog breach freezes NEW non-safety BUY orders; it never liquidates.
G7：章程停機。K1／K3／K4 違規只凍結「非安全的新買單」，絕不清倉。

R3 money path, so it fails closed:
  * the gate (``order_allowed`` / ``trading_allowed``) reads ``charter_state``; an unreadable state blocks the BUY;
  * while frozen / human_stop only strategies on the mission.yaml ``frozen_exit_whitelist`` (ADR-005) may trade, BUY and
    SELL alike; the shared StrategyRegistry.is_safety_control list is NOT the gate list (it also names buying
    strategies);
  * an unreadable state or whitelist never traps a position: a SELL is allowed and marked
    ``charter_unreadable_sell_allowed`` (logged at error), a BUY stays blocked;
  * ``human_stop`` stays until a human releases it; the watchdog never clears it;
  * the three manual ``ai_trading_enabled = true`` writers do not touch this table, so they cannot lift a freeze.
Known, accepted trade-off (ADR-003 operator decision): ``transactions`` has no strategy column, so K3 cannot separate
safety exits from other sells and may freeze more often than necessary. Frozen never closes a position.
Clock contract: every function takes ``now``; time columns are written explicitly; no SQL NOW().
這是 R3 金錢路徑，故 fail-closed：狀態讀不到就擋買單；凍結或人工停止時只有 mission.yaml 白名單（ADR-005）內的策略
能下單，買賣皆然；狀態或白名單讀不到時賣單放行並標記 charter_unreadable_sell_allowed，不把人困在部位裡；human_stop 只有人能解；
三處手動 ai_trading_enabled=true 不動本表，因此無法解除凍結。K3 無法分離安全出場（transactions 無策略欄），
可能多凍結，已被操作者接受；凍結不清倉。
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from sqlalchemy import func, update
from sqlalchemy.orm import sessionmaker

from src.config.mission import load_mission
from src.data.charter_models import CharterState
from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

HALTING_KS = ("K1", "K3", "K4")
BLOCKING_MODES = ("frozen", "human_stop")
BUY_ACTIONS = ("BUY", "STRONG_BUY", "ADD", "ACCUMULATE")     # same set as UnifiedRiskGateway.is_buy / 與風控閘門一致
SELL_ACTIONS = ("SELL", "TRIM", "REDUCE", "EXIT")            # orders that reduce a position / 減碼類動作
UNREADABLE_SELL_MARK = "charter_unreadable_sell_allowed"     # visible to the caller, see order_allowed

# emit(kind, key, payload): writes the charter_events row and sends the realtime notice (charter_digest_service.
# notify_event, bound by the task shell; injected here so this module stays import-light). / 由任務外殼綁定。
Emit = Callable[[str, Optional[str], Dict[str, Any]], None]


@dataclass(frozen=True)
class State:
    mode: str
    human_stop: bool
    reason: Optional[str]
    since: Optional[datetime]
    clears_on: Optional[date]
    breach_ids: Tuple[str, ...]
    resume_mode: Optional[str]


def read_state(engine: Any = None) -> State:
    """The singleton row. Raises when the database or the row is unavailable (callers decide; the gate fails closed).
    單列狀態；資料庫或列不存在就 raise。"""
    with sessionmaker(bind=engine or get_db_engine())() as s:
        row = s.query(CharterState).filter(CharterState.id == 1).first()
        if row is None:
            raise LookupError("charter_state row missing")
        return State(row.mode, bool(row.human_stop), row.reason, row.since, row.clears_on,
                     tuple(row.breach_ids or ()), row.resume_mode)


def trading_allowed(engine: Any, now: datetime) -> Tuple[bool, str]:
    """May a NEW non-safety BUY go out right now? (False, reason) when frozen / human_stop / state unreadable.
    ``now`` is part of the clock contract; the decision depends on the stored state only.
    現在能不能下新的非安全買單？凍結、人工停止、狀態讀不到都回 (False, 原因)。"""
    try:
        st = read_state(engine)
    except Exception as e:
        logger.warning("charter_state unreadable, blocking non-safety BUY (fail closed): %s", e)
        return False, f"charter_state unreadable: {type(e).__name__}"
    if st.human_stop or st.mode in BLOCKING_MODES:
        return False, f"charter {st.mode}: {st.reason}"
    return True, "ok"


def frozen_exit_whitelist() -> frozenset:
    """Strategies a frozen charter still lets through (mission.yaml ``frozen_exit_whitelist``, ADR-005), normalised.
    Raises when the mission file cannot be read; the caller decides (the gate fails closed for BUY).
    凍結時仍放行的策略（mission.yaml 白名單，已正規化）；讀不到就 raise。"""
    return frozenset(str(n).strip().lower() for n in load_mission().frozen_exit_whitelist)


def order_allowed(action: str, strategy_name: Optional[str], now: datetime, engine: Any = None) -> Tuple[bool, str]:
    """Gate for one order (ADR-005). Anything that is not a BUY- or SELL-type action is exempt. A strategy on the
    ``frozen_exit_whitelist`` is exempt without reading the state; every other order needs ``trading_allowed``.
    Fail-closed asymmetry: an unreadable state or whitelist blocks a BUY but lets a SELL through, marked
    ``charter_unreadable_sell_allowed`` and logged at error, because blocking a SELL could trap a position.
    單筆訂單閘門：非買賣動作免檢；白名單策略免讀狀態；其餘需 trading_allowed。讀不到時買單擋、賣單放行並標記。"""
    act = str(action).upper().strip()
    is_buy, is_sell = act in BUY_ACTIONS, act in SELL_ACTIONS
    if not (is_buy or is_sell):
        return True, "exempt: not an order"
    name = (strategy_name or "").strip().lower()

    def unreadable(what: str) -> Tuple[bool, str]:
        if is_sell:
            logger.error("charter gate: %s unreadable, allowing SELL %r (marked %s)",
                         what, name or "(none)", UNREADABLE_SELL_MARK)
            return True, f"{UNREADABLE_SELL_MARK}: {what} unreadable"
        logger.warning("charter gate: %s unreadable, blocking BUY (fail closed)", what)
        return False, f"charter {what} unreadable"

    try:
        whitelist = frozen_exit_whitelist()
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as e:
        logger.error("charter gate: frozen_exit_whitelist unreadable (%s: %s)", type(e).__name__, e)
        return unreadable("whitelist")
    if name in whitelist:
        return True, "exempt: frozen exit whitelist"
    try:
        eng = engine or get_db_engine()
    except Exception as e:
        logger.warning("charter gate: no database engine (%s)", e)
        return unreadable("state")
    ok, why = trading_allowed(eng, now)
    if ok:
        return True, why
    if why.startswith("charter_state unreadable"):
        return unreadable("state")
    return False, f"{why}; strategy {name or '(none)'} is not on the frozen exit whitelist"


def _emit(emit: Optional[Emit], kind: str, payload: Dict[str, Any]) -> None:
    """The state change is already committed; a failed notice is logged loudly, not allowed to undo or hide it."""
    if emit is None:
        return
    try:
        emit(kind, None, payload)
    except Exception as e:
        logger.error("charter %s recorded in charter_state but event/notice failed: %s", kind, e)


def _latest_clears_on(result: Dict[str, Any], hits: List[str]) -> Optional[date]:
    """Latest structured clears_on among the breaching K3/K4 rows; None when any is unknown (display only). / 僅供顯示。"""
    dates: List[date] = []
    for row in result.get("criteria", []):
        if row.get("id") in hits and row.get("id") in ("K3", "K4"):
            if not row.get("clears_on"):
                return None
            dates.append(date.fromisoformat(row["clears_on"]))
    return max(dates) if dates else None


def apply_watchdog(result: Dict[str, Any], now: datetime, engine: Any, emit: Optional[Emit] = None) -> Optional[str]:
    """Watchdog ``evaluate()`` result -> charter_state transition. Returns 'freeze' | 'resume' | None.
    Freeze: a K1/K3/K4 breach while not frozen and no human stop. Resume: no halting breach remains (a K that is merely not
    measurable is not a breach, so it does not keep the freeze: a freeze nobody can lift would be worse). K2/K5/K6/K7
    never freeze. Raises when the state is unreadable. / 看門狗結果 → 狀態轉移；讀不到狀態就 raise。"""
    st = read_state(engine)
    breaches = set(result.get("breaches", []))
    hits = [k for k in HALTING_KS if k in breaches]
    with sessionmaker(bind=engine)() as s:
        if hits and st.mode not in BLOCKING_MODES and not st.human_stop:
            clr = _latest_clears_on(result, hits)
            reason = f"watchdog breach {hits}"
            n = s.execute(update(CharterState).where(
                CharterState.id == 1, CharterState.human_stop.is_(False), CharterState.mode.notin_(BLOCKING_MODES)
            ).values(resume_mode=CharterState.mode, mode="frozen", breach_ids=hits, clears_on=clr, reason=reason,
                     since=now, updated_at=now)).rowcount
            s.commit()
            if not n:
                return None
            _emit(emit, "freeze", {"breach_ids": hits, "clears_on": clr.isoformat() if clr else None, "resume_mode": st.mode, "reason": reason})
            return "freeze"
        if not hits and st.mode == "frozen" and not st.human_stop:
            back = st.resume_mode if st.resume_mode in ("dry_run", "apply", "tighten_only") else "dry_run"
            n = s.execute(update(CharterState).where(
                CharterState.id == 1, CharterState.human_stop.is_(False), CharterState.mode == "frozen"
            ).values(mode=back, resume_mode=None, breach_ids=None, clears_on=None, reason="watchdog clear",
                     since=now, updated_at=now)).rowcount
            s.commit()
            if not n:
                return None
            _emit(emit, "resume", {"resumed_to": back, "cleared": list(st.breach_ids)})
            return "resume"
    return None


def human_stop(engine: Any, now: datetime, reason: str, emit: Optional[Emit] = None) -> None:
    """Emergency stop: mode 'human_stop' and the flag, keeping the mode to return to. Only a human clears it."""
    with sessionmaker(bind=engine)() as s:
        n = s.execute(update(CharterState).where(CharterState.id == 1).values(
            resume_mode=func.coalesce(
                func.nullif(func.nullif(CharterState.mode, "human_stop"), "frozen"), CharterState.resume_mode),
            mode="human_stop", human_stop=True, reason=f"human stop: {reason}", since=now, updated_at=now)).rowcount
        s.commit()
    if not n:
        raise LookupError("charter_state row missing")
    _emit(emit, "freeze", {"source": "human", "reason": reason})


def human_release(engine: Any, now: datetime, emit: Optional[Emit] = None) -> None:
    """Clear only the human flag; mode returns to resume_mode (or dry_run). A still-present K breach re-freezes on the
    next ``apply_watchdog`` pass. / 只清人工旗標；仍有違規則下次看門狗再凍結。"""
    st = read_state(engine)
    if not (st.human_stop or st.mode == "human_stop"):
        return                                   # nothing human to release; never lift a watchdog freeze / 不動看門狗凍結
    back = st.resume_mode if st.resume_mode in ("dry_run", "apply", "tighten_only") else "dry_run"
    if st.mode not in BLOCKING_MODES:
        back = st.mode
    with sessionmaker(bind=engine)() as s:
        s.execute(update(CharterState).where(CharterState.id == 1).values(
            mode=back, human_stop=False, resume_mode=None, breach_ids=None, clears_on=None,
            reason="human release", since=now, updated_at=now))
        s.commit()
    _emit(emit, "resume", {"source": "human", "resumed_to": back})
