"""
Shadow-mode wiring of the proposal validator on the Sentinel event path (WP5).
Sentinel 事件路徑的提案驗證器 shadow 模式接線（WP5）。

SHADOW means: every event-path signal is validated and RECORDED (trade_proposals + counterfactual
decision_outcomes), and nothing else. The legacy executor still receives exactly the arguments it always did;
this module never returns a verdict the caller can act on.
Shadow 的意思：每個事件訊號都被驗證並「記錄」，僅此而已；執行器收到的參數與過去完全相同，
本模組不回傳任何可供呼叫端據以行動的判定。

Rules this module keeps / 本模組遵守的規則:
  * The proposal handed to the validator carries ONLY non-numeric LLM fields (ticker, direction, rationale,
    intent). The LLM's quantity / score are kept apart under `legacy_call_args` in the evidence blob.
  * Inside, an error is never turned into an approval: a crash is recorded as status 'rejected' with
    reject_reason 'validator_error' (and no counterfactual rows — nothing was actually decided).
  * Errors are swallowed ONLY at the outer call boundary (logged at WARNING), so shadow cannot break trading.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

from src.config.mission import load_mission
from src.services.order_cap_policy import single_order_cap_usd
from src.services.proposal_validator import ValidationContext, ValidationResult, validate
from src.services.threshold_band_recorder import build_observation, record_at_boundary

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "wp4-v1"
SOURCE = "event"
STRATEGY_ID = "proposal_event"
COUNTERFACTUAL_AGENT = "proposal_shadow"
COUNTERFACTUAL_HORIZONS = (5, 63)
GATEWAY_TIMEOUT_S = 30
VALIDATOR_ERROR = "validator_error"
# Frozen: the five safety exits that may bypass the replacement-plan rule. / 凍結的五個安全出場名稱。
SAFETY_EXIT_NAMES = frozenset(
    {"stop_loss", "trailing_stop_loss", "trailing_stop", "emergency_exit", "macro_volatility_hedge"}
)
MODE_OFF = "off"
MODE_SHADOW = "shadow"
SETTING_MODE = "trade_proposal_mode"


# ── mode ──────────────────────────────────────────────────────────────────────

def resolve_trade_proposal_mode(settings_service: Any) -> str:
    """'off' or 'shadow'. 'enforce', unknown or unreadable values behave as 'shadow' (never change orders).
    只回 'off' 或 'shadow'；enforce／未知／讀不到都當 shadow，絕不改變下單。"""
    try:
        raw = settings_service.get_setting(SETTING_MODE)
    except Exception as exc:
        logger.warning("proposal_shadow: %s unreadable (%s); behaving as shadow", SETTING_MODE, exc)
        return MODE_SHADOW
    mode = raw.strip().lower() if isinstance(raw, str) else None
    if mode in (MODE_OFF, MODE_SHADOW):
        return mode
    if mode == "enforce":
        logger.warning("proposal_shadow: %s=enforce is not implemented yet; behaving as shadow", SETTING_MODE)
    else:
        logger.warning("proposal_shadow: %s=%r is not a valid mode; behaving as shadow", SETTING_MODE, raw)
    return MODE_SHADOW


# ── pure helpers ──────────────────────────────────────────────────────────────

def idempotency_key(*, user_id: str, ticker: str, direction: str, source: str, day: date, rationale: str) -> str:
    """sha256(user|ticker|direction|source|UTC date|rationale-hash). Repeated alerts the same day collapse.
    同一天的重複警報會收斂成同一把鍵。"""
    rationale_hash = hashlib.sha256((rationale or "").encode("utf-8")).hexdigest()
    raw = "|".join([str(user_id), str(ticker), str(direction), str(source), day.isoformat(), rationale_hash])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _finite_positive(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _num_or_none(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _research_age_days(ts: Any) -> Optional[float]:
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return None
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - ts).total_seconds() / 86400.0, 0.0)


def make_research_lookup(user_id: str, repo: Any) -> Callable[[str], Optional[Tuple[float, float]]]:
    """(score_0_to_10, age_days) from the newest ticker_research row, or None. Stored 0-1 scores are x10
    (same rule as confidence_rebalance_service._latest_score). / 最新研究列；0-1 分數乘 10；沒有就 None。"""
    def lookup(ticker: str) -> Optional[Tuple[float, float]]:
        rows = repo.get_research(user_id, ticker, limit=1)
        if not rows:
            return None
        row = rows[0]
        raw = row.get("confidence_score")
        if not raw:
            return None
        score = _num_or_none(raw)
        age = _research_age_days(row.get("created_at"))
        if score is None or age is None:
            return None
        return (score * 10.0 if score <= 1.0 else score, age)
    return lookup


# ── default (production) dependencies, all overridable through `deps` ─────────

async def _default_account(user_id: str) -> Tuple[float, float]:
    from src.services.broker_factory import BrokerFactory
    broker = BrokerFactory.get_broker(user_id)
    if not broker:
        raise RuntimeError("broker unavailable")
    account = await broker.get_account()
    return float(getattr(account, "total_equity", 0.0) or 0.0), float(getattr(account, "available_cash", 0.0) or 0.0)


def _default_holdings(user_id: str) -> Dict[str, float]:
    from src.services.transaction_service import TransactionService
    held = TransactionService().get_holdings_map(user_id)
    return {str(t).upper(): float((d or {}).get("quantity", 0) or 0) for t, d in held.items()}


def _default_sells_today(engine: Any, user_id: str) -> Tuple[int, float]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(DISTINCT ticker), COALESCE(SUM(amount), 0) FROM transactions "
                 "WHERE user_id = :uid AND action = 'SELL' AND entry_category = 'trade' AND trade_date = :d"),
            {"uid": user_id, "d": datetime.now(timezone.utc).date()},
        ).fetchone()
    return int(row[0] or 0), float(row[1] or 0.0)


def _make_price_lookup(settings_service: Any, deps: Dict[str, Any]) -> Callable[[str], Any]:
    if deps.get("price_lookup"):
        return deps["price_lookup"]

    async def lookup(ticker: str) -> Optional[float]:
        mds = deps.get("market_service")
        if mds is None:
            from src.services.market_data_service import MarketDataService
            mds = MarketDataService(settings_service=settings_service)
        prices = await mds.get_current_prices([ticker])
        return _finite_positive((prices or {}).get(ticker.upper()))
    return lookup


async def _build_shared(user_id: str, need_sells: bool, settings_service: Any, deps: Dict[str, Any],
                        engine: Any) -> Dict[str, Any]:
    """Everything deterministic that is the same for every signal of this call. Raises on any failure; the
    caller records that as validator_error rather than guessing.
    同一次呼叫內所有訊號共用的決定性輸入；任何失敗都拋出，由呼叫端記成 validator_error，不猜值。"""
    from src.services.capital_policy import tradable_capital

    nlv, available_cash = await (deps.get("account") or _default_account)(user_id)
    tradable = tradable_capital(user_id, nlv, settings_repo=deps.get("settings_repo"))
    holdings = deps["holdings"] if "holdings" in deps else await asyncio.to_thread(_default_holdings, user_id)
    if "research_lookup" in deps:
        research = deps["research_lookup"]
    else:
        from src.repositories.ticker_universe_repository import TickerUniverseRepository
        research = make_research_lookup(user_id, deps.get("research_repo") or TickerUniverseRepository())
    sold_count, sold_amount = 0, 0.0
    if need_sells:
        fn = deps.get("sells_today") or (lambda: _default_sells_today(engine, user_id))
        sold_count, sold_amount = await asyncio.to_thread(fn)
    gateway = deps.get("gateway")
    if gateway is None:
        from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService
        gateway = UnifiedRiskGatewayService(user_id=user_id)
    return {
        "tradable": float(tradable),
        # The executor bounds cash by tradable capital too (automated_trading_service BUY sizing guard).
        # 執行器同樣以可交易資本限縮現金。
        "cash": min(float(available_cash), float(tradable)),
        "mission": deps.get("mission") or load_mission(),
        "holdings": holdings,
        "research": research,
        "max_age": float(settings_service.get_setting("universe_research_max_age_days")),
        "per_order_cap": single_order_cap_usd(settings_service, None),
        "parking": _as_bool(settings_service.get_setting("benchmark_parking_enabled")),
        "sold_count": sold_count,
        "sold_amount": sold_amount,
        "gateway": gateway,
    }


def _build_context(shared: Dict[str, Any], loop: asyncio.AbstractEventLoop) -> ValidationContext:
    gateway = shared["gateway"]

    def gateway_check(ticker: str, direction: str, amount: float, strategy_name: str, score: float) -> Any:
        # Runs in a worker thread; the (async) gateway runs on the event loop so the loop is never blocked.
        # 在工作執行緒中執行；非同步 gateway 回到事件迴圈上跑，迴圈不會被卡住。
        fut = asyncio.run_coroutine_threadsafe(
            gateway.evaluate_trade_risk(ticker=ticker, action=direction, amount_usd=amount,
                                        strategy_name=strategy_name, confidence_score=score),
            loop,
        )
        try:
            return fut.result(timeout=GATEWAY_TIMEOUT_S)
        except BaseException:
            fut.cancel()
            raise

    return ValidationContext(
        tradable_capital_usd=shared["tradable"],
        usable_cash_usd=shared["cash"],
        mission=shared["mission"],
        held_positions=shared["holdings"],
        paired_buys=[],
        research_lookup=shared["research"],
        max_research_age_days=shared["max_age"],
        gateway_check=gateway_check,
        benchmark_parking_available=shared["parking"],
        per_order_cap_usd=shared["per_order_cap"],
        safety_exit_names=SAFETY_EXIT_NAMES,
        sold_today_count=shared["sold_count"],
        sold_today_amount=shared["sold_amount"],
    )


# ── persistence ───────────────────────────────────────────────────────────────

_INSERT_PROPOSAL = text("""
    INSERT INTO trade_proposals
        (id, user_id, source, strategy_id, ticker, direction, rationale_text, evidence, mode, status,
         reject_reason, sized_amount_usd, validator_version, idempotency_key)
    VALUES
        (:id, :user_id, :source, :strategy_id, :ticker, :direction, :rationale_text, :evidence, 'shadow', :status,
         :reject_reason, :sized_amount_usd, :validator_version, :idempotency_key)
    ON CONFLICT (user_id, source, ticker, direction, idempotency_key) DO NOTHING
""")
_EXISTS = text("""
    SELECT 1 FROM trade_proposals
    WHERE user_id = :user_id AND source = :source AND ticker = :ticker AND direction = :direction
      AND idempotency_key = :key
""")
_INSERT_COUNTERFACTUAL = text("""
    INSERT INTO decision_outcomes
        (id, user_id, agent_name, ticker, signal, price_at_decision, horizon_days,
         proposal_id, strategy_id, source, is_counterfactual)
    VALUES
        (:id, :user_id, :agent_name, :ticker, :signal, :price, :horizon_days,
         :proposal_id, :strategy_id, :source, :cf)
""")


def _persist(engine: Any, row: Dict[str, Any], counterfactuals: List[Dict[str, Any]]) -> bool:
    """One transaction: the proposal row and, only if it is new, its counterfactual rows. True if inserted.
    同一交易寫入提案列；僅在確實新增時才寫反事實列。"""
    with engine.begin() as conn:
        inserted = conn.execute(_INSERT_PROPOSAL, row).rowcount == 1
        if inserted:
            for cf in counterfactuals:
                conn.execute(_INSERT_COUNTERFACTUAL, {**cf, "proposal_id": row["id"], "user_id": row["user_id"]})
        return inserted


def _exists(engine: Any, user_id: str, ticker: str, direction: str, key: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(_EXISTS, {"user_id": user_id, "source": SOURCE, "ticker": ticker,
                                      "direction": direction, "key": key}).fetchone() is not None


async def _record_band(user_id: str, signal: Dict[str, Any], ticker: str, direction: str, settings_service: Any,
                       engine: Any, price_lookup: Callable[[str], Any]) -> None:
    """G1: record this signal against the auto-execute threshold in force (passed or not). Recording only.
    G1：把此訊號連同當時的自動執行門檻記下來（無論通過與否）；僅記錄。"""
    if direction not in ("BUY", "SELL"):
        return
    key = "auto_trade_threshold_sell" if direction == "SELL" else "auto_trade_threshold"
    default = 6.0 if direction == "SELL" else 7.5
    raw = settings_service.get_setting(key, default, user_id)
    threshold = _num_or_none(default if raw is None else raw)
    if threshold is None:
        logger.warning("proposal_shadow: %s=%r is unreadable; band observation for %s skipped", key, raw, ticker)
        return
    threshold = threshold / 10.0 if threshold > 10 else threshold  # UI stores 0-100 / UI 以 0-100 儲存
    score = _num_or_none(signal.get("score"))
    score = score / 10.0 if score is not None and score > 10 else score
    ob = build_observation(ticker=ticker, direction=direction, score=score, threshold=threshold,
                           context={"intent": str(signal.get("intent") or "")})
    await record_at_boundary(user_id, key, "event_shadow", [ob], settings_service=settings_service,
                             engine=engine, price_lookup=price_lookup)


# ── main entry ────────────────────────────────────────────────────────────────

async def record_shadow_proposals(
    user_id: str,
    signals: List[Dict[str, Any]],
    source_label: str,
    *,
    settings_service: Any = None,
    deps: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate and record each signal. Returns nothing; swallows (and warns about) any failure at this boundary.
    驗證並記錄每個訊號；不回傳任何東西，任何失敗只在此邊界以 WARNING 記錄並吞掉。"""
    try:
        await _record(user_id, signals, source_label, settings_service, deps or {})
    except Exception as exc:
        logger.warning("proposal_shadow: recording failed (trading unaffected): %s", exc)


async def _record(user_id: str, signals: List[Dict[str, Any]], source_label: str,
                  settings_service: Any, deps: Dict[str, Any]) -> None:
    if not signals:
        return
    if settings_service is None:
        from src.services.settings_service import SettingsService
        settings_service = SettingsService(user_id=user_id)
    engine = deps.get("engine")
    if engine is None:
        from src.data.database import get_db_engine
        engine = get_db_engine()
    price_lookup = _make_price_lookup(settings_service, deps)
    loop = asyncio.get_running_loop()

    shared: Optional[Dict[str, Any]] = None
    shared_error: Optional[str] = None
    try:
        need_sells = any(str(s.get("action", "")).upper() == "SELL" for s in signals)
        shared = await _build_shared(user_id, need_sells, settings_service, deps, engine)
    except Exception as exc:
        shared_error = f"context: {exc}"
        logger.warning("proposal_shadow: could not build validation context: %s", exc)

    for signal in signals:
        try:
            await _record_one(user_id, signal, source_label, shared, shared_error, loop, engine, price_lookup,
                              settings_service)
        except Exception as exc:
            logger.warning("proposal_shadow: could not record %s %s: %s",
                           signal.get("action"), signal.get("ticker"), exc)


async def _record_one(user_id: str, signal: Dict[str, Any], source_label: str, shared: Optional[Dict[str, Any]],
                      shared_error: Optional[str], loop: asyncio.AbstractEventLoop, engine: Any,
                      price_lookup: Callable[[str], Any], settings_service: Any) -> None:
    ticker = str(signal.get("ticker", "")).strip().upper()
    direction = str(signal.get("action", "")).strip().upper()
    try:
        await _record_band(user_id, signal, ticker, direction, settings_service, engine, price_lookup)
    except Exception as exc:  # a recorder fault must not stop proposal recording / 紀錄器故障不得阻斷提案紀錄
        logger.warning("proposal_shadow: band observation failed for %s %s: %s", direction, ticker, exc)
    reason = str(signal.get("reason") or "")
    intent = str(signal.get("intent") or "")
    # Only non-numeric LLM fields reach the validator. / 只有非數值的 LLM 欄位會進驗證器。
    proposal = {"source": SOURCE, "direction": direction, "ticker": ticker, "rationale_text": reason,
                "evidence": {"intent": intent, "council_source": str(source_label)}}
    key = idempotency_key(user_id=user_id, ticker=ticker, direction=direction, source=SOURCE,
                          day=datetime.now(timezone.utc).date(), rationale=reason)
    if await asyncio.to_thread(_exists, engine, user_id, ticker, direction, key):
        logger.info("proposal_shadow: duplicate %s %s today; not re-recorded", direction, ticker)
        return

    error: Optional[str] = shared_error
    result: Optional[ValidationResult] = None
    if shared is not None:
        try:
            result = await asyncio.to_thread(validate, proposal, _build_context(shared, loop))
        except Exception as exc:
            error = f"validate: {exc}"
            logger.warning("proposal_shadow: validator crashed for %s %s: %s", direction, ticker, exc)

    approved = result is not None and result.approved
    reason_code = "approved" if approved else (result.reason if result is not None else VALIDATOR_ERROR)
    evidence: Dict[str, Any] = {
        **proposal["evidence"],
        # Legacy numbers are record-keeping only; names deliberately avoid the validator's forbidden keys.
        # 舊路徑數字僅供留存；鍵名刻意避開驗證器的禁用名稱。
        "legacy_call_args": {"qty_requested": _num_or_none(signal.get("quantity")),
                             "conf_requested": _num_or_none(signal.get("score"))},
    }
    if result is not None:
        evidence["validator"] = {"reason": result.reason, "validated_score": result.score,
                                 "sized_usd": result.amount_usd, "strategy": result.strategy_name,
                                 "planned_buys": [dict(b) for b in result.planned_buys]}
    if error is not None:
        evidence["error"] = error

    cf_rows: List[Dict[str, Any]] = []
    if result is not None and not approved:
        price = None
        try:
            price = _finite_positive(await price_lookup(ticker))
        except Exception as exc:
            logger.warning("proposal_shadow: price lookup failed for %s: %s", ticker, exc)
        if price is None:
            logger.warning("proposal_shadow: no price for %s; counterfactual rows skipped for this proposal", ticker)
        else:
            cf_rows = [{"id": str(uuid.uuid4()), "agent_name": COUNTERFACTUAL_AGENT, "ticker": ticker,
                        "signal": direction, "price": price, "horizon_days": h, "strategy_id": STRATEGY_ID,
                        "source": SOURCE, "cf": True} for h in COUNTERFACTUAL_HORIZONS]

    row = {
        "id": str(uuid.uuid4()), "user_id": user_id, "source": SOURCE, "strategy_id": STRATEGY_ID,
        "ticker": ticker, "direction": direction, "rationale_text": reason,
        "evidence": json.dumps(evidence, ensure_ascii=False, default=str),
        "status": "approved" if approved else "rejected",
        "reject_reason": None if approved else reason_code,
        "sized_amount_usd": result.amount_usd if approved else None,
        "validator_version": VALIDATOR_VERSION, "idempotency_key": key,
    }
    inserted = await asyncio.to_thread(_persist, engine, row, cf_rows)
    logger.info("proposal_shadow: %s %s -> %s (%s)%s", direction, ticker, row["status"], reason_code,
                "" if inserted else " [duplicate, not stored]")
