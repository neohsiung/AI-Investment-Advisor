"""G7 on real Postgres: the charter halt. The watchdog is replaced by a fixed evaluate() result; everything else
(charter_state, charter_events, the gate, the risk gateway, migration 033) is real.
G7 在真實 Postgres：章程停機。看門狗換成固定的 evaluate() 結果，其餘（狀態表、事件表、閘門、風控閘門、遷移 033）皆為真實。
"""
import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.services import charter_digest_service as cds
from src.services import charter_state_service as css
from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService

from .factories import USER_ID, set_charter_state

REPO = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.charter_e2e, pytest.mark.real_charter_gate]

NONSAFETY = "batch_cash_deployment"


def _watchdog(*breaches, status=None, clears_on=None):
    """A fixed ``MissionWatchdogService.evaluate()`` result. / 固定的看門狗結果。"""
    ids = ("K1", "K2", "K3", "K4", "K5", "K6", "K7")
    st = dict.fromkeys(ids, "ok")
    st.update({k: "breach" for k in breaches})
    st.update(status or {})
    return {"overall": "BREACH" if breaches else "OK", "breaches": list(breaches),
            "criteria": [{"id": k, "status": st[k], "clears_on": (clears_on or {}).get(k)} for k in ids]}


class _Pipe:
    """The task shell's emitter with the notifier replaced by a recorder: real charter_events row, recorded notice."""

    def __init__(self, engine, now_fn):
        self.engine, self.now_fn, self.titles = engine, now_fn, []

    def __call__(self, kind, key, payload):
        cds.notify_event(self.engine, USER_ID, kind, key, payload, self.now_fn(),
                         notify=lambda title, body: self.titles.append(kind))


def _state(engine):
    with engine.connect() as c:
        return dict(c.execute(text("SELECT mode, human_stop, resume_mode, breach_ids, clears_on, updated_at "
                                   "FROM charter_state WHERE id = 1")).mappings().one())


def _events(engine, kind):
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM charter_events WHERE kind = :k"), {"k": kind}).scalar()


def _freeze(engine, clock, *breaches, pipe=None, **kw):
    return css.apply_watchdog(_watchdog(*breaches, **kw), clock.now(), engine, pipe)


async def test_k1_breach_freezes_then_nonsafety_buy_refused_and_stop_loss_exit_allowed(pg_engine, frozen_clock):
    set_charter_state(pg_engine, "apply")
    pipe = _Pipe(pg_engine, frozen_clock.now)
    assert _freeze(pg_engine, frozen_clock, "K1", pipe=pipe) == "freeze"
    assert _state(pg_engine)["mode"] == "frozen" and _state(pg_engine)["resume_mode"] == "apply"
    assert _events(pg_engine, "freeze") == 1 and pipe.titles == ["freeze"]

    now = frozen_clock.now()
    assert css.order_allowed("BUY", NONSAFETY, now, pg_engine)[0] is False
    assert css.order_allowed("SELL", "stop_loss", now, pg_engine) == (True, "exempt: not a buy")      # exits keep working
    assert css.order_allowed("SELL", NONSAFETY, now, pg_engine)[0] is True                           # never trap a position
    assert css.order_allowed("BUY", "benchmark_parking", now, pg_engine)[0] is True                  # safety control

    with patch("src.services.charter_state_service.get_db_engine", return_value=pg_engine):
        res = await UnifiedRiskGatewayService(user_id=USER_ID).evaluate_trade_risk(
            ticker="NVDA", action="BUY", amount_usd=100.0, current_price=100.0, strategy_name=NONSAFETY,
            confidence_score=9.0)
    assert res.allowed is False and res.primary_blocker == "CharterHalt"


async def test_manual_resume_paths_cannot_clear_charter_state(pg_engine, frozen_clock):
    """The three writers of ai_trading_enabled=true (webhook /resume, actionable alert resume_trading, protections
    reset_lockout) are driven for real with only SettingsService replaced; charter_state must not move.
    三個寫 ai_trading_enabled=true 的路徑真的被呼叫（僅替換 SettingsService）；charter_state 不得變動。"""
    set_charter_state(pg_engine, "apply")
    _freeze(pg_engine, frozen_clock, "K3")
    before = _state(pg_engine)

    from src.services.actionable_alert_service import ActionableAlertHubService
    from src.services.trading_protections_service import TradingProtectionsService
    from src.services.webhook_service import telegram_bot_webhook

    ss = MagicMock()
    ss.find_user_by_channel_id.return_value = USER_ID
    ss.get_setting.return_value = ""                                  # no bot token: _reply returns at once
    request = MagicMock()

    async def _json():
        return {"message": {"chat": {"id": 42}, "text": "/resume"}}
    request.json = _json
    with patch("src.services.settings_service.SettingsService", return_value=ss):
        assert (await ActionableAlertHubService(USER_ID).execute_action("resume_trading"))["ok"] is True
        TradingProtectionsService(user_id=USER_ID).reset_lockout()
        await telegram_bot_webhook(request)
        await asyncio.sleep(0.2)                                      # the /resume handler runs as a task
    writes = [c.args for c in ss.save_setting.call_args_list if c.args[0] == "ai_trading_enabled"]
    assert writes.count(("ai_trading_enabled", "true")) == 3

    assert _state(pg_engine) == before and before["mode"] == "frozen"
    assert css.order_allowed("BUY", NONSAFETY, frozen_clock.now(), pg_engine)[0] is False


def test_human_stop_has_priority_over_watchdog_clear(pg_engine, frozen_clock):
    set_charter_state(pg_engine, "apply")
    _freeze(pg_engine, frozen_clock, "K1")
    css.human_stop(pg_engine, frozen_clock.now(), "operator")
    assert _state(pg_engine)["mode"] == "human_stop" and _state(pg_engine)["resume_mode"] == "apply"
    for _ in range(3):                                                # clear, then breach again: neither moves it
        frozen_clock.advance(days=1)
        assert css.apply_watchdog(_watchdog(), frozen_clock.now(), pg_engine) is None
        assert css.apply_watchdog(_watchdog("K1"), frozen_clock.now(), pg_engine) is None
    assert _state(pg_engine)["human_stop"] is True
    assert css.order_allowed("BUY", NONSAFETY, frozen_clock.now(), pg_engine)[0] is False
    css.human_release(pg_engine, frozen_clock.now())
    assert (_state(pg_engine)["mode"], _state(pg_engine)["human_stop"]) == ("apply", False)
    assert css.order_allowed("BUY", NONSAFETY, frozen_clock.now(), pg_engine)[0] is True


def test_freeze_resume_cycle_restores_resume_mode(pg_engine, frozen_clock):
    set_charter_state(pg_engine, "tighten_only")
    pipe = _Pipe(pg_engine, frozen_clock.now)
    assert _freeze(pg_engine, frozen_clock, "K3", "K4", pipe=pipe,
                   clears_on={"K3": "2026-10-25", "K4": "2026-10-28"}) == "freeze"
    assert str(_state(pg_engine)["clears_on"]) == "2026-10-28" and _state(pg_engine)["breach_ids"] == ["K3", "K4"]

    frozen_clock.advance(days=2)                                      # still breaching: nothing new
    assert _freeze(pg_engine, frozen_clock, "K3", pipe=pipe) is None
    frozen_clock.advance(days=8)                                      # past clears_on, K3/K4 ok again
    assert _freeze(pg_engine, frozen_clock, pipe=pipe) == "resume"
    st = _state(pg_engine)
    assert (st["mode"], st["resume_mode"], st["breach_ids"], st["clears_on"]) == ("tighten_only", None, None, None)
    assert _events(pg_engine, "freeze") == 1 and _events(pg_engine, "resume") == 1
    assert pipe.titles == ["freeze", "resume"]
    assert css.order_allowed("BUY", NONSAFETY, frozen_clock.now(), pg_engine)[0] is True


def test_unreadable_state_fails_closed(pg_engine, frozen_clock, caplog):
    now = frozen_clock.now()
    with pg_engine.begin() as c:
        c.execute(text("DELETE FROM charter_state"))
    with caplog.at_level(logging.WARNING):
        assert css.order_allowed("BUY", NONSAFETY, now, pg_engine)[0] is False
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert css.order_allowed("SELL", NONSAFETY, now, pg_engine)[0] is True
    assert css.order_allowed("BUY", "stop_loss", now, pg_engine)[0] is True
    with pytest.raises(Exception):
        css.apply_watchdog(_watchdog("K1"), now, pg_engine)

    set_charter_state(pg_engine, "apply")
    unreachable = create_engine("postgresql+psycopg2://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    assert css.order_allowed("BUY", NONSAFETY, now, unreachable)[0] is False


def test_033_upgrade_downgrade_roundtrip(pg_engine, pg_url, monkeypatch):
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "alembic"))
    monkeypatch.setenv("DB_URL", pg_url)
    new_cols = {"clears_on", "breach_ids", "resume_mode", "updated_at"}
    flags = {n: lg.disabled for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}

    def cols():
        return {c["name"] for c in inspect(pg_engine).get_columns("charter_state")}
    set_charter_state(pg_engine, "frozen", reason="roundtrip")
    try:
        command.downgrade(cfg, "032_charter_events")
        assert not (new_cols & cols())
        with pg_engine.connect() as c:                                 # the row and its mode survive the downgrade
            assert c.execute(text("SELECT mode FROM charter_state WHERE id = 1")).scalar() == "frozen"
        command.upgrade(cfg, "head")
        assert new_cols <= cols()
        with pg_engine.connect() as c:
            row = c.execute(text("SELECT mode, clears_on, breach_ids, resume_mode, updated_at FROM charter_state "
                                 "WHERE id = 1")).one()
        assert row == ("frozen", None, None, None, None)
    finally:
        command.upgrade(cfg, "head")
        for n, disabled in flags.items():
            logging.getLogger(n).disabled = disabled
    assert new_cols <= cols()
