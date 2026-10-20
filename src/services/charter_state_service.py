"""G7: the charter halt. A K1/K3/K4 watchdog breach freezes NEW non-safety BUY orders; it never liquidates.
G7：章程停機。K1／K3／K4 違規只凍結「非安全的新買單」，絕不清倉。

R3 money path, so it fails closed:
  * the gate (``order_allowed`` / ``trading_allowed``) reads ``charter_state`` and an unreadable state blocks the BUY;
  * SELL is never blocked, and safety-control strategies (StrategyRegistry.is_safety_control: stop_loss,
    benchmark_parking, ...) keep working while frozen;
  * ``human_stop`` stays until a human releases it; the watchdog never clears it;
  * the three manual ``ai_trading_enabled = true`` writers do not touch this table, so they cannot lift a freeze.
Known, accepted trade-off (ADR-003 operator decision): ``transactions`` has no strategy column, so K3 cannot separate
safety exits from other sells and may freeze more often than necessary. Frozen never closes a position.
Clock contract: every function takes ``now``; time columns are written explicitly; no SQL NOW().
這是 R3 金錢路徑，故 fail-closed：狀態讀不到就擋買單；賣單與安全控制策略永遠放行；human_stop 只有人能解；
三處手動 ai_trading_enabled=true 不動本表，因此無法解除凍結。K3 無法分離安全出場（transactions 無策略欄），
可能多凍結，已被操作者接受；凍結不清倉。
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, update
from sqlalchemy.orm import sessionmaker

from src.data.charter_models import CharterState
from src.data.database import get_db_engine
from src.services.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)

HALTING_KS = ("K1", "K3", "K4")
BLOCKING_MODES = ("frozen", "human_stop")
BUY_ACTIONS = ("BUY", "STRONG_BUY", "ADD", "ACCUMULATE")     # same set as UnifiedRiskGateway.is_buy / 與風控閘門一致

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


def order_allowed(action: str, strategy_name: Optional[str], now: datetime, engine: Any = None) -> Tuple[bool, str]:
    """Gate for one order: SELL and safety controls are exempt without reading the state; every other BUY-type
    action needs ``trading_allowed``. / 單筆訂單閘門：賣單與安全控制免讀狀態直接放行，其他買入類動作需 trading_allowed。"""
    if str(action).upper().strip() not in BUY_ACTIONS:
        return True, "exempt: not a buy"
    if StrategyRegistry.is_safety_control(strategy_name or ""):
        return True, "exempt: safety control"
    try:
        eng = engine or get_db_engine()
    except Exception as e:
        logger.warning("charter gate: no database engine, blocking non-safety BUY (fail closed): %s", e)
        return False, f"charter_state unreadable: {type(e).__name__}"
    return trading_allowed(eng, now)


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
