"""Charter E2E factories: seed rows through the REAL recorders, settle by direct UPDATE (never the real resolver).
章程 E2E 工廠：透過真實記錄器寫入、以直接 UPDATE 結算（絕不跑真實 resolver，它用 SQL NOW() 且需要網路）。"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.services import rotation_pair_recorder as rpr
from src.services import threshold_band_recorder as tbr

USER_ID = "charter_e2e_user"
ALLOWED_HOSTS = ("localhost", "127.0.0.1")
TRUNCATE_TABLES = ("parameter_values", "parameter_changes", "parameter_trials", "threshold_band_observations",
                   "rotation_pair_observations", "decision_outcomes")


def validate_pg_url(url: str) -> str:
    """Refuse anything that is not a local throwaway database. pytest.exit, not skip: a wrong target must be loud.
    只允許本機一次性資料庫；不符就 pytest.exit（不是 skip），目標錯了必須大聲。"""
    u = make_url(url)
    name = u.database or ""
    if u.host not in ALLOWED_HOSTS:
        pytest.exit(f"charter_e2e refuses host {u.host!r}: only {ALLOWED_HOSTS} are allowed", returncode=2)
    if not (name == "portfolio" or name.startswith("charter_e2e")):
        pytest.exit(f"charter_e2e refuses database {name!r}: only 'portfolio' (ci_local container) or "
                    "'charter_e2e*' are allowed", returncode=2)
    return url


def resolve_pg_url() -> Optional[str]:
    """CHARTER_E2E_PG_URL, else GitHub-Actions DB_* (creating database charter_e2e), else None.
    CHARTER_E2E_PG_URL → GitHub Actions 的 DB_*（自建 charter_e2e）→ None。"""
    explicit = os.getenv("CHARTER_E2E_PG_URL")
    if explicit:
        return validate_pg_url(explicit)
    if os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("DB_HOST"):
        base = make_url("postgresql+psycopg2://").set(
            username=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASS", "postgres"),
            host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "portfolio"))
        validate_pg_url(base.render_as_string(hide_password=False))
        admin = create_engine(base, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = 'charter_e2e'")).fetchone():
                c.execute(text("CREATE DATABASE charter_e2e"))
        admin.dispose()
        return validate_pg_url(base.set(database="charter_e2e").render_as_string(hide_password=False))
    return None


class FrozenClock:
    """freezegun wrapper for code that calls datetime.now(); advance(days=) moves it forward.
    以 freezegun 包裝，給呼叫 datetime.now() 的程式；advance(days=) 往前推。"""

    def __init__(self, start: datetime):
        self._now = start
        self._frozen = freeze_time(start, tick=False)

    def start(self) -> "FrozenClock":
        self._frozen.start()
        return self

    def stop(self) -> None:
        self._frozen.stop()

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, days: float = 0, hours: float = 0) -> datetime:
        from datetime import timedelta
        self._now = self._now + timedelta(days=days, hours=hours)
        self._frozen.stop()
        self._frozen = freeze_time(self._now, tick=False)
        self._frozen.start()
        return self._now


class NotifySink:
    """Injected in place of a notifier: records every message instead of sending it. / 取代通知器，只記錄不送出。"""

    def __init__(self) -> None:
        self.messages: List[Tuple[str, Dict[str, Any]]] = []

    def __call__(self, message: str, **kwargs: Any) -> None:
        self.messages.append((message, kwargs))


class ClosesProvider:
    """Injected in place of market data: per-ticker close series set by the test. A ticker nobody set raises KeyError
    (no invented prices). / 取代行情來源；沒設定的 ticker 會 KeyError，不虛構價格。"""

    def __init__(self) -> None:
        self._closes: Dict[str, List[float]] = {}

    def set(self, ticker: str, closes: Sequence[float]) -> None:
        self._closes[ticker.upper()] = [float(c) for c in closes]

    def __call__(self, ticker: str, days: Optional[int] = None) -> List[float]:
        series = self._closes[ticker.upper()]
        return series if days is None else series[-days:]


def _price_lookup(price: float) -> Callable[[str], Any]:
    async def lookup(_ticker: str) -> float:
        return price
    return lookup


def _noon_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


def seed_band_obs(engine: Any, key: str, obs_date: date, rows: Sequence[Tuple[str, float, float]], *,
                  direction: str = "BUY", price: float = 100.0, source_service: str = "charter_e2e",
                  user_id: str = USER_ID) -> tbr.RecordStats:
    """rows = [(ticker, score, threshold)]. Calls the real record_band_observations with the wall clock frozen at
    obs_date, so obs_date and the two counterfactual outcome rows (5d, 63d) are exactly what production writes.
    以牆上時鐘凍結在 obs_date 呼叫真實記錄器，obs_date 與兩筆反事實列和正式環境寫的一致。"""
    obs = [tbr.build_observation(ticker=t, direction=direction, score=s, threshold=thr) for t, s, thr in rows]
    with freeze_time(_noon_utc(obs_date), tick=False):
        return asyncio.run(tbr.record_band_observations(engine, user_id, key, source_service, obs,
                                                        _price_lookup(price)))


def seed_rotation_pair(engine: Any, obs_date: date, *, sell_ticker: str = "SSS", buy_ticker: str = "BBB",
                       holding_score: float = 5.0, candidate_score: float = 8.0, holding_age_days: float = 10.0,
                       min_score_delta: float = 2.0, min_holding_days: float = 5.0, friction_pct: Optional[float] = 1.0,
                       decision: str = "swap_approved", price: float = 100.0, user_id: str = USER_ID) -> rpr.PairStats:
    pair = rpr.build_pair(sell_ticker=sell_ticker, buy_ticker=buy_ticker, holding_score=holding_score,
                          candidate_score=candidate_score, holding_age_days=holding_age_days,
                          min_score_delta=min_score_delta, min_holding_days=min_holding_days,
                          friction_pct=friction_pct, decision=decision)
    with freeze_time(_noon_utc(obs_date), tick=False):
        return asyncio.run(rpr.record_rotation_pair(engine, user_id, pair, _price_lookup(price)))


def settle(engine: Any, *, source: str, horizon_days: int, alpha_pct: Optional[float] = None,
           realized_return_pct: Optional[float] = None, resolved_at: datetime,
           decided_at: Optional[datetime] = None, proposal_id: Optional[str] = None, ticker: Optional[str] = None,
           signal: Optional[str] = None) -> int:
    """Direct UPDATE of the resolver's output columns on matching counterfactual rows; returns rows touched.
    直接 UPDATE resolver 的輸出欄位；回傳更新列數。"""
    sets = ["resolved_at = :resolved_at", "alpha_pct = :alpha_pct", "realized_return_pct = :ret"]
    params: Dict[str, Any] = {"resolved_at": resolved_at, "alpha_pct": alpha_pct, "ret": realized_return_pct,
                              "src": source, "h": horizon_days}
    if decided_at is not None:
        sets.append("decided_at = :decided_at")
        params["decided_at"] = decided_at
    where = ["source = :src", "horizon_days = :h", "is_counterfactual = TRUE"]
    for col, val in (("proposal_id", proposal_id), ("ticker", ticker), ("signal", signal)):
        if val is not None:
            where.append(f"{col} = :{col}")
            params[col] = val
    sql = f"UPDATE decision_outcomes SET {', '.join(sets)} WHERE {' AND '.join(where)}"  # noqa: S608 fixed fragments
    with engine.begin() as conn:
        return conn.execute(text(sql), params).rowcount


def set_charter_state(engine: Any, mode: str = "dry_run", *, reason: str = "charter_e2e", human_stop: bool = False,
                      since: Optional[datetime] = None) -> None:
    """Upsert the singleton row with an explicit `since` (no server_default reliance). / 明確指定 since。"""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO charter_state (id, mode, reason, since, human_stop) VALUES (1, :m, :r, :s, :h) "
            "ON CONFLICT (id) DO UPDATE SET mode = :m, reason = :r, since = :s, human_stop = :h"),
            {"m": mode, "r": reason, "s": since or datetime(2026, 1, 1, tzinfo=timezone.utc), "h": human_stop})
