"""WP5: shadow-mode proposal recording on the event path (DB writes + logs only).
WP5：事件路徑的 shadow 模式提案紀錄（只寫 DB 與 log，不影響下單）。"""
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.config.mission import load_mission
from src.services import proposal_shadow_service as pss
from src.services import proposal_validator as pv


@pytest.fixture
def anyio_backend():
    return "asyncio"


DDL = [
    """CREATE TABLE trade_proposals (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, source TEXT NOT NULL, strategy_id TEXT,
        ticker TEXT NOT NULL, direction TEXT NOT NULL, rationale_text TEXT, evidence TEXT,
        llm_model TEXT, mode TEXT NOT NULL DEFAULT 'shadow', status TEXT NOT NULL DEFAULT 'proposed',
        reject_reason TEXT, sized_amount_usd NUMERIC, validator_version TEXT,
        idempotency_key TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, source, ticker, direction, idempotency_key))""",
    """CREATE TABLE decision_outcomes (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT, agent_name TEXT NOT NULL,
        ticker TEXT NOT NULL, signal TEXT NOT NULL, price_at_decision NUMERIC NOT NULL,
        decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, horizon_days INTEGER NOT NULL DEFAULT 5,
        resolved_at TIMESTAMP, proposal_id TEXT, strategy_id TEXT, source TEXT,
        is_counterfactual BOOLEAN NOT NULL DEFAULT 0)""",
    """CREATE TABLE threshold_band_observations (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, threshold_key TEXT NOT NULL,
        source_service TEXT NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
        obs_date DATE NOT NULL, score NUMERIC, threshold_value NUMERIC NOT NULL, margin NUMERIC,
        passed BOOLEAN, in_band BOOLEAN NOT NULL, price NUMERIC, data_marker TEXT, context TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, threshold_key, source_service, ticker, direction, obs_date))""",
]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as c:
        for stmt in DDL:
            c.execute(text(stmt))
    return eng


class _Repo:
    def get(self, user_id, key):
        return {"tradable_capital_pct": 75, "tradable_capital_usd": 0}.get(key)


def _settings(**over):
    values = {"universe_research_max_age_days": 14, "batch_deploy_max_order_usd": 100.0,
              "benchmark_parking_enabled": False, "trade_proposal_mode": "shadow"}
    values.update(over)
    svc = MagicMock()
    svc.get_setting.side_effect = lambda key, default=None, user_id=None: values.get(key, default)
    return svc


class _Gateway:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []
        self.thread_ids = []

    async def evaluate_trade_risk(self, **kw):
        self.calls.append(kw)
        self.thread_ids.append(threading.get_ident())
        return SimpleNamespace(allowed=self.allowed, reasons=[], guard_details={})


def _deps(engine, **over):
    async def account(user_id):
        return 10000.0, 5000.0

    async def price(ticker):
        return 100.0

    d = {"engine": engine, "account": account, "settings_repo": _Repo(), "holdings": {"AAPL": 3.0},
         "research_lookup": lambda t: (7.0, 1.0), "gateway": _Gateway(), "price_lookup": price,
         "sells_today": lambda: (0, 0.0)}
    d.update(over)
    return d


def _sig(**over):
    s = {"ticker": "MSFT", "action": "BUY", "quantity": 123.456, "score": 9, "intent": "auto",
         "reason": "Sentinel Council: add on dip"}
    s.update(over)
    return s


def _rows(engine, table):
    """decision_outcomes here means the proposal ledger's rows; G1 band rows are read via _band_outcomes.
    此處 decision_outcomes 指提案帳本的列；G1 門檻帶列用 _band_outcomes 讀。"""
    where = " WHERE agent_name != 'threshold_band'" if table == "decision_outcomes" else ""
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(f"SELECT * FROM {table}{where}")).mappings()]


def _band_outcomes(engine):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(
            text("SELECT * FROM decision_outcomes WHERE agent_name = 'threshold_band'")).mappings()]


def _walk_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _walk_keys(v)


# ── approved / rejected persistence ───────────────────────────────────────────

@pytest.mark.anyio
async def test_approved_writes_one_shadow_row_and_no_counterfactuals(engine):
    await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=_deps(engine))
    rows = _rows(engine, "trade_proposals")
    assert len(rows) == 1
    r = rows[0]
    assert (r["mode"], r["status"], r["source"], r["direction"], r["ticker"]) == ("shadow", "approved", "event", "BUY", "MSFT")
    assert r["validator_version"] == "wp4-v1"
    assert r["reject_reason"] is None
    assert float(r["sized_amount_usd"]) == pytest.approx(min(7500 * load_mission().promotion.max_initial_live_weight_pct / 100, 100.0, 5000.0))
    assert r["rationale_text"] == "Sentinel Council: add on dip"
    assert _rows(engine, "decision_outcomes") == []


@pytest.mark.anyio
async def test_rejected_writes_exactly_two_counterfactual_rows(engine):
    deps = _deps(engine, gateway=_Gateway(allowed=False))
    await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=deps)
    (p,) = _rows(engine, "trade_proposals")
    assert p["status"] == "rejected" and p["reject_reason"] == "gateway_blocked"
    assert p["sized_amount_usd"] is None
    cf = _rows(engine, "decision_outcomes")
    assert sorted(r["horizon_days"] for r in cf) == [5, 63]
    for r in cf:
        assert bool(r["is_counterfactual"]) is True
        assert r["proposal_id"] == p["id"]
        assert (r["strategy_id"], r["source"], r["signal"], r["ticker"]) == ("proposal_event", "event", "BUY", "MSFT")
        assert float(r["price_at_decision"]) == 100.0
        assert r["resolved_at"] is None


@pytest.mark.anyio
async def test_sell_without_replacement_is_rejected_with_sell_signal(engine):
    deps = _deps(engine)
    await pss.record_shadow_proposals("u1", [_sig(ticker="AAPL", action="SELL")], "sentinel",
                                      settings_service=_settings(), deps=deps)
    (p,) = _rows(engine, "trade_proposals")
    assert p["status"] == "rejected" and p["reject_reason"] == "no_replacement_plan"
    assert {r["signal"] for r in _rows(engine, "decision_outcomes")} == {"SELL"}


@pytest.mark.anyio
async def test_same_signal_twice_same_day_is_one_row_and_two_counterfactuals(engine):
    deps = _deps(engine, gateway=_Gateway(allowed=False))
    for _ in range(2):
        await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=deps)
    assert len(_rows(engine, "trade_proposals")) == 1
    assert len(_rows(engine, "decision_outcomes")) == 2


@pytest.mark.anyio
async def test_missing_price_skips_counterfactual_rows_and_logs(engine):
    async def no_price(ticker):
        return None

    deps = _deps(engine, gateway=_Gateway(allowed=False), price_lookup=no_price)
    with patch.object(pss, "logger") as log:
        await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=deps)
    assert len(_rows(engine, "trade_proposals")) == 1
    assert _rows(engine, "decision_outcomes") == []
    assert any("price" in str(c).lower() for c in log.warning.call_args_list + log.info.call_args_list)


@pytest.mark.anyio
async def test_validator_crash_is_recorded_as_rejected_validator_error_without_counterfactuals(engine):
    with patch.object(pss, "validate", side_effect=RuntimeError("boom")), patch.object(pss, "logger") as log:
        await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=_deps(engine))
    (p,) = _rows(engine, "trade_proposals")
    assert (p["status"], p["reject_reason"]) == ("rejected", "validator_error")
    assert "boom" in p["evidence"]
    assert _rows(engine, "decision_outcomes") == []
    assert log.warning.called


@pytest.mark.anyio
async def test_context_build_failure_is_rejected_validator_error_never_approved(engine):
    async def broken(user_id):
        raise RuntimeError("broker down")

    await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(),
                                      deps=_deps(engine, account=broken))
    (p,) = _rows(engine, "trade_proposals")
    assert (p["status"], p["reject_reason"]) == ("rejected", "validator_error")


@pytest.mark.anyio
async def test_unwritable_db_is_swallowed_at_the_boundary_with_warning():
    class BadEngine:
        def connect(self):
            raise RuntimeError("db is gone")

        begin = connect

    with patch.object(pss, "logger") as log:
        out = await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(),
                                                deps=_deps(BadEngine()))
    assert out is None
    assert any("db is gone" in str(c) for c in log.warning.call_args_list)


# ── proposal shape / purity ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_proposal_has_no_forbidden_keys_or_llm_numbers_and_legacy_numbers_are_stored_apart(engine):
    seen = []
    real_validate = pv.validate

    def spy(proposal, ctx):
        seen.append(proposal)
        return real_validate(proposal, ctx)

    with patch.object(pss, "validate", side_effect=spy):
        await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(), deps=_deps(engine))
    (proposal,) = seen
    assert proposal == {"source": "event", "direction": "BUY", "ticker": "MSFT",
                        "rationale_text": "Sentinel Council: add on dip",
                        "evidence": {"intent": "auto", "council_source": "sentinel"}}
    keys = {k.strip().lower() for k in _walk_keys(proposal)}
    assert not keys & pv.FORBIDDEN_LLM_KEYS
    assert "123.456" not in json.dumps(proposal)
    (row,) = _rows(engine, "trade_proposals")
    evidence = json.loads(row["evidence"])
    assert evidence["legacy_call_args"] == {"qty_requested": 123.456, "conf_requested": 9}
    assert not {k.strip().lower() for k in _walk_keys(evidence)} & pv.FORBIDDEN_LLM_KEYS


@pytest.mark.anyio
async def test_signals_are_not_mutated(engine):
    sigs = [_sig(), _sig(ticker="NVDA")]
    before = json.dumps(sigs, sort_keys=True)
    await pss.record_shadow_proposals("u1", sigs, "sentinel", settings_service=_settings(), deps=_deps(engine))
    assert json.dumps(sigs, sort_keys=True) == before


@pytest.mark.anyio
async def test_gateway_runs_on_the_event_loop_thread_while_validate_runs_in_a_worker(engine):
    gw = _Gateway()
    validate_threads = []
    real_validate = pv.validate

    def spy(proposal, ctx):
        validate_threads.append(threading.get_ident())
        return real_validate(proposal, ctx)

    with patch.object(pss, "validate", side_effect=spy):
        await pss.record_shadow_proposals("u1", [_sig()], "sentinel", settings_service=_settings(),
                                          deps=_deps(engine, gateway=gw))
    assert gw.calls and gw.thread_ids[0] == threading.get_ident()
    assert validate_threads and validate_threads[0] != threading.get_ident()
    assert gw.calls[0]["ticker"] == "MSFT" and gw.calls[0]["action"] == "BUY"


def test_idempotency_key_depends_on_user_ticker_direction_source_date_and_rationale():
    from datetime import date
    base = dict(user_id="u", ticker="MSFT", direction="BUY", source="event", day=date(2026, 10, 17), rationale="r")
    k = pss.idempotency_key(**base)
    assert len(k) == 64 and k == pss.idempotency_key(**base)
    for field, value in [("user_id", "v"), ("ticker", "AAPL"), ("direction", "SELL"), ("source", "strategy"),
                         ("day", date(2026, 10, 18)), ("rationale", "other")]:
        assert pss.idempotency_key(**{**base, field: value}) != k


# ── mode resolution ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [("off", "off"), ("shadow", "shadow"), (" OFF ", "off")])
def test_mode_known_values(raw, expected):
    assert pss.resolve_trade_proposal_mode(_settings(trade_proposal_mode=raw)) == expected


def test_mode_enforce_behaves_as_shadow_and_warns():
    with patch.object(pss, "logger") as log:
        assert pss.resolve_trade_proposal_mode(_settings(trade_proposal_mode="enforce")) == "shadow"
    assert any("enforce" in str(c).lower() for c in log.warning.call_args_list)


@pytest.mark.parametrize("raw", ["bogus", "", None, 7, MagicMock()])
def test_mode_garbage_behaves_as_shadow_and_warns(raw):
    svc = MagicMock()
    svc.get_setting.return_value = raw
    with patch.object(pss, "logger") as log:
        assert pss.resolve_trade_proposal_mode(svc) == "shadow"
    assert log.warning.called


def test_mode_unreadable_behaves_as_shadow_and_warns():
    svc = MagicMock()
    svc.get_setting.side_effect = RuntimeError("settings db down")
    with patch.object(pss, "logger") as log:
        assert pss.resolve_trade_proposal_mode(svc) == "shadow"
    assert any("settings db down" in str(c) for c in log.warning.call_args_list)


# ── G1: threshold band observations (recording only) ──────────────────────────

@pytest.mark.anyio
async def test_passing_signal_also_gets_counterfactual_row(engine):
    """An APPROVED proposal (no proposal-ledger counterfactual) still gets a band row + 2 outcome rows."""
    await pss.record_shadow_proposals("u1", [_sig(score=7.8)], "sentinel", settings_service=_settings(),
                                      deps=_deps(engine))
    assert _rows(engine, "decision_outcomes") == []
    (o,) = _rows(engine, "threshold_band_observations")
    assert (o["threshold_key"], o["source_service"], o["direction"]) == ("auto_trade_threshold", "event_shadow", "BUY")
    assert bool(o["passed"]) is True and float(o["score"]) == 7.8 and float(o["threshold_value"]) == 7.5
    assert sorted(r["horizon_days"] for r in _band_outcomes(engine)) == [5, 63]


@pytest.mark.anyio
async def test_sell_uses_sell_threshold_in_force_and_records_rejection(engine):
    settings = _settings(auto_trade_threshold_sell=6.5)
    await pss.record_shadow_proposals("u1", [_sig(ticker="AAPL", action="SELL", score=6.0)], "sentinel",
                                      settings_service=settings, deps=_deps(engine))
    (o,) = _rows(engine, "threshold_band_observations")
    assert o["threshold_key"] == "auto_trade_threshold_sell"
    assert bool(o["passed"]) is False and float(o["threshold_value"]) == 6.5 and float(o["margin"]) == -0.5


@pytest.mark.anyio
async def test_band_threshold_stored_on_0_100_ui_scale_is_normalised(engine):
    await pss.record_shadow_proposals("u1", [_sig(score=75)], "sentinel",
                                      settings_service=_settings(auto_trade_threshold=75), deps=_deps(engine))
    (o,) = _rows(engine, "threshold_band_observations")
    assert float(o["threshold_value"]) == 7.5 and float(o["score"]) == 7.5 and bool(o["passed"]) is True


@pytest.mark.anyio
async def test_missing_price_row_is_marked_and_counted(engine):
    async def no_price(ticker):
        return None

    with patch("src.services.threshold_band_recorder.logger") as log:
        await pss.record_shadow_proposals("u1", [_sig(score=7.8)], "sentinel", settings_service=_settings(),
                                          deps=_deps(engine, price_lookup=no_price))
    (o,) = _rows(engine, "threshold_band_observations")
    assert o["data_marker"] == "_insufficient_data:price" and o["price"] is None
    assert _band_outcomes(engine) == []
    assert any("missing_price" in c.args[0] and c.args[4] == 1 for c in log.warning.call_args_list)


@pytest.mark.anyio
async def test_signal_without_score_is_marked_not_defaulted(engine):
    sig = _sig()
    del sig["score"]
    await pss.record_shadow_proposals("u1", [sig], "sentinel", settings_service=_settings(), deps=_deps(engine))
    (o,) = _rows(engine, "threshold_band_observations")
    assert o["score"] is None and o["passed"] is None and o["data_marker"] == "_insufficient_data:score"


@pytest.mark.anyio
async def test_recorder_never_changes_decision_of_shadow_path(engine):
    """Same proposal row with the band table present or absent; a broken recorder does not stop recording."""
    deps = _deps(engine, gateway=_Gateway(allowed=False))
    with patch("src.services.proposal_shadow_service.record_at_boundary", side_effect=RuntimeError("boom")):
        await pss.record_shadow_proposals("u1", [_sig(score=7.8)], "sentinel", settings_service=_settings(), deps=deps)
    (p,) = _rows(engine, "trade_proposals")
    assert p["status"] == "rejected" and p["reject_reason"] == "gateway_blocked"
    assert len(_rows(engine, "decision_outcomes")) == 2
    assert _rows(engine, "threshold_band_observations") == []
