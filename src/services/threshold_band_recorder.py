"""
Threshold band recorder (charter milestone G1): evidence for self-adjustable score thresholds.
門檻帶紀錄器（章程 G1）：為可自我調整的分數門檻保存證據。

Why: a threshold such as batch_deploy_min_confidence or auto_trade_threshold_sell can only be loosened or
tightened on evidence about the *marginal band* — signals just above and just below it. Before this module
only REJECTED proposals got counterfactual outcome rows, and no row carried the score or the threshold in
force, so the band could not be measured. Here EVERY signal within BAND_HALFWIDTH of a threshold — passed or
rejected — is written with its score and the threshold value at that moment, plus two counterfactual
`decision_outcomes` rows (5d / 63d) so the existing resolver fills in return and alpha.
為何：只有「剛好高於／低於門檻」的訊號才能評估該不該調門檻。過去只有被拒提案有反事實列，且沒有任何一列
記錄分數與當時門檻。此處對門檻附近的每個訊號（通過或被拒）寫入分數、當時門檻與兩筆反事實列。

Rules / 規則:
  * RECORDING ONLY. Nothing here returns a verdict a caller can act on; it never changes a decision or order.
  * A missing score or price is never replaced by a default (AGENTS.md constraint 0). The row is written with
    an explicit `data_marker` and counted in the returned RecordStats and in a WARNING log line.
  * The writer raises on a database failure; the caller logs it at WARNING at its own boundary.
  * `decision_outcomes.proposal_id` of a band row holds the observation id and `source` is OUTCOME_SOURCE —
    it is NOT a trade_proposals id. Consumers already exclude counterfactual rows.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from sqlalchemy import text

from src.data.database import get_db_engine
from src.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

# Half-width of the recorded band, in score points. Wide enough to cover the registry bounds of the
# thresholds that use this recorder (config/parameter_registry.yaml). / 紀錄帶半寬（分數點）。
BAND_HALFWIDTH = 2.0
COUNTERFACTUAL_HORIZONS = (5, 63)
COUNTERFACTUAL_AGENT = "threshold_band"
OUTCOME_SOURCE = "threshold_band"
MARKER_NO_SCORE = "_insufficient_data:score"
MARKER_NO_PRICE = "_insufficient_data:price"


@dataclass(frozen=True)
class BandObservation:
    ticker: str
    direction: str
    score: Optional[float]
    threshold: float
    passed: Optional[bool]
    margin: Optional[float]
    in_band: bool
    data_marker: Optional[str]
    context: Optional[Dict[str, Any]] = None


@dataclass
class RecordStats:
    recorded: int = 0
    duplicates: int = 0
    missing_price: int = 0
    missing_score: int = 0
    outside_band: int = 0


def _finite(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_observation(*, ticker: str, direction: str, score: Any, threshold: float,
                      context: Optional[Dict[str, Any]] = None,
                      band_halfwidth: float = BAND_HALFWIDTH) -> BandObservation:
    """Pure. passed = score >= threshold (the rule every owner uses). A missing score is marked, not guessed.
    純函式。passed = score >= threshold；缺分數就標記，不猜。"""
    thr = float(threshold)
    s = _finite(score)
    t, d = str(ticker).strip().upper(), str(direction).strip().upper()
    if s is None:
        return BandObservation(t, d, None, thr, None, None, True, MARKER_NO_SCORE, context)
    margin = round(s - thr, 6)
    return BandObservation(t, d, s, thr, s >= thr, margin, abs(margin) <= band_halfwidth, None, context)


_INSERT_OBSERVATION = text("""
    INSERT INTO threshold_band_observations
        (id, user_id, threshold_key, source_service, ticker, direction, obs_date, score, threshold_value,
         margin, passed, in_band, price, data_marker, context)
    VALUES
        (:id, :user_id, :threshold_key, :source_service, :ticker, :direction, :obs_date, :score,
         :threshold_value, :margin, :passed, :in_band, :price, :data_marker, :context)
    ON CONFLICT (user_id, threshold_key, source_service, ticker, direction, obs_date) DO NOTHING
""")
_INSERT_OUTCOME = text("""
    INSERT INTO decision_outcomes
        (id, user_id, agent_name, ticker, signal, price_at_decision, horizon_days,
         proposal_id, strategy_id, source, is_counterfactual)
    VALUES
        (:id, :user_id, :agent_name, :ticker, :signal, :price, :horizon_days,
         :proposal_id, :strategy_id, :source, :cf)
""")


async def _price_or_none(price_lookup: Callable[[str], Awaitable[Any]], ticker: str) -> Optional[float]:
    try:
        p = _finite(await price_lookup(ticker))
    except Exception as exc:
        logger.warning("threshold_band: price lookup failed for %s: %s", ticker, exc)
        return None
    return p if p is not None and p > 0 else None


def _write(engine: Any, rows: List[Dict[str, Any]]) -> int:
    """One transaction. Outcome rows only for newly inserted observations. Returns inserted count.
    單一交易；只有新插入的觀察才寫反事實列。"""
    inserted = 0
    with engine.begin() as conn:
        for row in rows:
            outcomes = row.pop("_outcomes")
            if conn.execute(_INSERT_OBSERVATION, row).rowcount != 1:
                continue
            inserted += 1
            for o in outcomes:
                conn.execute(_INSERT_OUTCOME, {**o, "proposal_id": row["id"], "user_id": row["user_id"]})
    return inserted


async def record_band_observations(
    engine: Any,
    user_id: str,
    threshold_key: str,
    source_service: str,
    observations: Sequence[BandObservation],
    price_lookup: Callable[[str], Awaitable[Any]],
) -> RecordStats:
    """Write every in-band observation (and every unscored one, marked). Raises on a database failure.
    寫入所有帶內觀察（以及無分數者，附標記）；資料庫失敗時拋出。"""
    stats = RecordStats()
    today: date = datetime.now(timezone.utc).date()
    rows: List[Dict[str, Any]] = []
    for ob in observations:
        if not ob.in_band:
            stats.outside_band += 1
            continue
        marker = ob.data_marker
        price: Optional[float] = None
        if ob.score is None:
            stats.missing_score += 1
        else:
            price = await _price_or_none(price_lookup, ob.ticker)
            if price is None:
                marker = MARKER_NO_PRICE
                stats.missing_price += 1
        rows.append({
            "id": str(uuid.uuid4()), "user_id": user_id, "threshold_key": threshold_key,
            "source_service": source_service, "ticker": ob.ticker, "direction": ob.direction, "obs_date": today,
            "score": ob.score, "threshold_value": ob.threshold, "margin": ob.margin, "passed": ob.passed,
            "in_band": True, "price": price, "data_marker": marker,
            "context": json.dumps(ob.context, ensure_ascii=False, default=str) if ob.context else None,
            "_outcomes": [] if price is None else [
                {"id": str(uuid.uuid4()), "agent_name": COUNTERFACTUAL_AGENT, "ticker": ob.ticker,
                 "signal": ob.direction, "price": price, "horizon_days": h, "strategy_id": threshold_key,
                 "source": OUTCOME_SOURCE, "cf": True} for h in COUNTERFACTUAL_HORIZONS],
        })
    if rows:
        stats.recorded = len(rows)
        inserted = await asyncio.to_thread(_write, engine, rows)
        stats.duplicates = stats.recorded - inserted
        stats.recorded = inserted
    if stats.missing_price or stats.missing_score:
        logger.warning("threshold_band: %s/%s recorded=%d missing_price=%d missing_score=%d (rows carry data_marker)",
                       source_service, threshold_key, stats.recorded, stats.missing_price, stats.missing_score)
    return stats


def default_price_lookup(settings_service: Any) -> Callable[[str], Awaitable[Any]]:
    """Current price through MarketDataService; None when the feed has none (the caller marks it).
    以 MarketDataService 取現價；沒有就回 None（由紀錄器標記，不補預設）。"""
    mds = MarketDataService(settings_service=settings_service)

    async def lookup(ticker: str) -> Optional[float]:
        prices = await mds.get_current_prices([ticker])
        return _finite((prices or {}).get(ticker.upper()))
    return lookup


async def record_at_boundary(
    user_id: str,
    threshold_key: str,
    source_service: str,
    observations: Sequence[BandObservation],
    *,
    settings_service: Any,
    engine: Any = None,
    price_lookup: Optional[Callable[[str], Awaitable[Any]]] = None,
) -> Optional[RecordStats]:
    """Caller-side wrapper: a failure is logged at WARNING and returns None — never a fake RecordStats —
    so recording can never break the decision path it observes.
    呼叫端用的包裝：失敗以 WARNING 記錄並回 None（不回假統計），絕不拖累所觀察的決策路徑。"""
    if not observations:
        return None
    try:
        return await record_band_observations(
            engine if engine is not None else get_db_engine(), user_id, threshold_key, source_service,
            observations, price_lookup or default_price_lookup(settings_service))
    except Exception as exc:
        logger.warning("threshold_band: recording %s/%s failed (decision unaffected): %s",
                       source_service, threshold_key, exc)
        return None


def band_collector(direction: str, threshold: float):
    """(observer, sink): the observer plugs into rank_candidates and appends one BandObservation per candidate.
    (observer, sink)：observer 掛進 rank_candidates，每個候選加入一筆 BandObservation。"""
    sink: List[BandObservation] = []
    return (lambda t, c, ok: sink.append(build_observation(ticker=t, direction=direction, score=c,
                                                           threshold=threshold))), sink
