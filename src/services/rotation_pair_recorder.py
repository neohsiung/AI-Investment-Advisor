"""
Rotation pair recorder (charter milestone G1b): evidence for rotation_min_score_delta / rotation_min_holding_days.
換庫配對紀錄器（章程 G1b）：為 rotation_min_score_delta 與 rotation_min_holding_days 保存證據。

A rotation is only worth its threshold if (buy candidate return − sold holding return − round-trip friction) is
positive over 5d and 63d. So each rotation decision that reaches the swap test — approved, rejected on the score
gap, or blocked because the holding was too young — is written as ONE pair row linking the sell leg and the buy
leg, with the score gap, holding age, thresholds in force and the friction assumption read from
`rotation_roundtrip_friction_pct`. Both legs also get 5d/63d counterfactual `decision_outcomes` rows
(`proposal_id` = pair id, `source` = OUTCOME_SOURCE) so the existing resolver fills in return and alpha.
每次走到換庫判斷的決策（核准／分數差不足被拒／持有太短被擋）寫成一筆配對，連結賣出腿與買進腿，並各寫 5d/63d
反事實 outcome，讓既有 resolver 補報酬與 alpha。

Rules / 規則: RECORDING ONLY — nothing here returns a verdict a caller can act on. A missing score, age,
friction or price is never defaulted: the row carries `data_marker` (`_insufficient_data:<what>`), and a missing
price is counted in PairStats and in a WARNING. Boundary wrappers log failures at WARNING and return None.
"""
from __future__ import annotations

import asyncio
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from sqlalchemy import text

from src.data.database import get_db_engine
from src.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

DECISION_APPROVED = "swap_approved"
DECISION_REJECTED_DELTA = "swap_rejected_delta"
DECISION_BLOCKED_YOUNG = "blocked_min_holding"
COUNTERFACTUAL_AGENT = "rotation_pair"
OUTCOME_SOURCE = "rotation_pair"
COUNTERFACTUAL_HORIZONS = (5, 63)
FRICTION_SETTING = "rotation_roundtrip_friction_pct"
MARKER = "_insufficient_data:"


@dataclass(frozen=True)
class RotationPair:
    sell_ticker: str
    buy_ticker: str
    decision: str
    holding_score: Optional[float]
    candidate_score: Optional[float]
    score_delta: Optional[float]
    holding_age_days: Optional[float]
    min_score_delta: float
    min_holding_days: float
    friction_pct: Optional[float]
    data_marker: Optional[str]


@dataclass
class PairStats:
    recorded: int = 0
    duplicates: int = 0
    missing_price: int = 0


def _finite(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_pair(*, sell_ticker: str, buy_ticker: str, holding_score: Any, candidate_score: Any,
               holding_age_days: Any, min_score_delta: float, min_holding_days: float, friction_pct: Any,
               decision: str) -> RotationPair:
    """Pure. Any missing input stays None and sets the marker. / 純函式；缺值保持 None 並設標記。"""
    hs, cs, age, fr = _finite(holding_score), _finite(candidate_score), _finite(holding_age_days), _finite(friction_pct)
    marker = None
    for name, ok in (("score", hs is not None and cs is not None), ("age", age is not None),
                     ("friction", fr is not None)):
        if not ok:
            marker = MARKER + name
            break
    delta = round(cs - hs, 6) if hs is not None and cs is not None else None
    return RotationPair(str(sell_ticker).strip().upper(), str(buy_ticker).strip().upper(), decision, hs, cs, delta,
                        age, float(min_score_delta), float(min_holding_days), fr, marker)


def read_friction_pct(settings_service: Any) -> Optional[float]:
    """Friction assumption from the setting; None when unreadable (the pair is then marked). / 讀不到回 None。"""
    try:
        v = _finite(settings_service.get_setting(FRICTION_SETTING))
    except Exception as exc:
        logger.warning("rotation_pair: %s unreadable: %s", FRICTION_SETTING, exc)
        return None
    return v if v is not None and v >= 0 else None


_INSERT_PAIR = text("""
    INSERT INTO rotation_pair_observations
        (id, user_id, obs_date, sell_ticker, buy_ticker, decision, holding_score, candidate_score, score_delta,
         holding_age_days, min_score_delta, min_holding_days, friction_pct, sell_price, buy_price, data_marker)
    VALUES
        (:id, :user_id, :obs_date, :sell_ticker, :buy_ticker, :decision, :holding_score, :candidate_score,
         :score_delta, :holding_age_days, :min_score_delta, :min_holding_days, :friction_pct, :sell_price,
         :buy_price, :data_marker)
    ON CONFLICT (user_id, sell_ticker, buy_ticker, obs_date, decision) DO NOTHING
""")
_INSERT_OUTCOME = text("""
    INSERT INTO decision_outcomes
        (id, user_id, agent_name, ticker, signal, price_at_decision, horizon_days,
         proposal_id, strategy_id, source, is_counterfactual)
    VALUES
        (:id, :user_id, :agent_name, :ticker, :signal, :price, :horizon_days,
         :proposal_id, :strategy_id, :source, true)
""")


def _write(engine: Any, row: Dict[str, Any], legs: List[Dict[str, Any]]) -> bool:
    with engine.begin() as conn:
        if conn.execute(_INSERT_PAIR, row).rowcount != 1:
            return False
        for leg in legs:
            conn.execute(_INSERT_OUTCOME, {**leg, "user_id": row["user_id"], "proposal_id": row["id"]})
        return True


async def _price(lookup: Callable[[str], Awaitable[Any]], ticker: str) -> Optional[float]:
    try:
        p = _finite(await lookup(ticker))
    except Exception as exc:
        logger.warning("rotation_pair: price lookup failed for %s: %s", ticker, exc)
        return None
    return p if p is not None and p > 0 else None


async def record_rotation_pair(engine: Any, user_id: str, pair: RotationPair,
                               price_lookup: Callable[[str], Awaitable[Any]]) -> PairStats:
    """Write one pair row (+ four outcome rows when BOTH prices exist). Raises on a database failure.
    寫一筆配對（兩腿價格都有才寫四筆 outcome）；資料庫失敗時拋出。"""
    stats = PairStats()
    sell_p, buy_p = await _price(price_lookup, pair.sell_ticker), await _price(price_lookup, pair.buy_ticker)
    marker = pair.data_marker
    if sell_p is None or buy_p is None:
        stats.missing_price = 1
        missing = "+".join(n for n, p in (("sell", sell_p), ("buy", buy_p)) if p is None)
        marker = f"{MARKER}price:{missing}"
    row = {"id": str(uuid.uuid4()), "user_id": user_id, "obs_date": datetime.now(timezone.utc).date(),
           "sell_ticker": pair.sell_ticker, "buy_ticker": pair.buy_ticker, "decision": pair.decision,
           "holding_score": pair.holding_score, "candidate_score": pair.candidate_score,
           "score_delta": pair.score_delta, "holding_age_days": pair.holding_age_days,
           "min_score_delta": pair.min_score_delta, "min_holding_days": pair.min_holding_days,
           "friction_pct": pair.friction_pct, "sell_price": sell_p, "buy_price": buy_p, "data_marker": marker}
    legs: List[Dict[str, Any]] = []
    if sell_p is not None and buy_p is not None:
        for signal, ticker, price in (("SELL", pair.sell_ticker, sell_p), ("BUY", pair.buy_ticker, buy_p)):
            legs += [{"id": str(uuid.uuid4()), "agent_name": COUNTERFACTUAL_AGENT, "ticker": ticker,
                      "signal": signal, "price": price, "horizon_days": h, "strategy_id": "rotation_pair",
                      "source": OUTCOME_SOURCE} for h in COUNTERFACTUAL_HORIZONS]
    inserted = await asyncio.to_thread(_write, engine, row, legs)
    stats.recorded, stats.duplicates = int(inserted), int(not inserted)
    if stats.missing_price:
        logger.warning("rotation_pair: %s->%s recorded=%d missing_price=%d (row carries data_marker)",
                       pair.sell_ticker, pair.buy_ticker, stats.recorded, stats.missing_price)
    return stats


def _default_price_lookup(settings_service: Any) -> Callable[[str], Awaitable[Any]]:
    mds = MarketDataService(settings_service=settings_service)

    async def lookup(ticker: str) -> Optional[float]:
        prices = await mds.get_current_prices([ticker])
        return _finite((prices or {}).get(ticker.upper()))
    return lookup


async def record_pairs_at_boundary(user_id: str, pairs: Sequence[RotationPair], *, settings_service: Any = None,
                                   engine: Any = None,
                                   price_lookup: Optional[Callable[[str], Awaitable[Any]]] = None) -> None:
    """Caller-side wrapper: failures are logged at WARNING and swallowed; never a fake result.
    呼叫端包裝：失敗以 WARNING 記錄並吞掉，絕不回假結果。"""
    try:
        eng = engine if engine is not None else get_db_engine()
        lookup = price_lookup or _default_price_lookup(settings_service)
        for p in pairs:
            await record_rotation_pair(eng, user_id, p, lookup)
    except Exception as exc:
        logger.warning("rotation_pair: recording failed (rotation decision unaffected): %s", exc)


async def record_rotation_decision(user_id: str, settings_service: Any, sell_ticker: str, buy_ticker: str,
                                   holding_score: Any, candidate_score: Any, holding_age_days: Any,
                                   min_score_delta: float, min_holding_days: float, decision: str) -> None:
    """Sentinel hook for a pair that reached the swap test. / 走到換庫判斷的配對。"""
    pair = build_pair(sell_ticker=sell_ticker, buy_ticker=buy_ticker, holding_score=holding_score,
                      candidate_score=candidate_score, holding_age_days=holding_age_days,
                      min_score_delta=min_score_delta, min_holding_days=min_holding_days,
                      friction_pct=read_friction_pct(settings_service), decision=decision)
    await record_pairs_at_boundary(user_id, [pair], settings_service=settings_service)


async def record_young_blocked(user_id: str, settings_service: Any, young: Dict[str, float], buy_ticker: str,
                               candidate_score: Any, score_lookup: Callable[[str], Any], min_score_delta: float,
                               min_holding_days: float, *, engine: Any = None,
                               price_lookup: Optional[Callable[[str], Awaitable[Any]]] = None) -> None:
    """Sentinel hook for holdings blocked by rotation_min_holding_days (age known, below the minimum).
    被 rotation_min_holding_days 擋下的持倉（年齡已知但不足）。"""
    if not young:
        return
    friction = read_friction_pct(settings_service)
    pairs = []
    for ticker, age in young.items():
        try:
            hs = score_lookup(ticker)
        except Exception as exc:
            logger.warning("rotation_pair: holding score lookup failed for %s: %s", ticker, exc)
            hs = None
        pairs.append(build_pair(sell_ticker=ticker, buy_ticker=buy_ticker, holding_score=hs,
                                candidate_score=candidate_score, holding_age_days=age,
                                min_score_delta=min_score_delta, min_holding_days=min_holding_days,
                                friction_pct=friction, decision=DECISION_BLOCKED_YOUNG))
    await record_pairs_at_boundary(user_id, pairs, settings_service=settings_service, engine=engine,
                                   price_lookup=price_lookup)
