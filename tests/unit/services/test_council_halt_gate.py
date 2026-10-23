"""No council for a news alert on an unheld ticker while the charter halt is on. / 停機中不為未持有標的的新聞警報開議會。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.models import Base, CharterState
from src.services import council_halt_gate as gate

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Base.metadata.tables["charter_state"]])
    return eng


def _state(eng, mode="frozen", human_stop=False):
    with sessionmaker(bind=eng)() as s:
        s.query(CharterState).delete()
        s.add(CharterState(id=1, mode=mode, reason="t", since=NOW - timedelta(days=1), human_stop=human_stop))
        s.commit()


def _tx(holdings):
    tx = MagicMock()
    tx.get_holdings_map.return_value = holdings
    return tx


NEWS = {"id": "news_AMZN_0.80", "text": "AMZN news", "priority": 2}


def _run(eng, trigger=None, holdings=None, ticker="AMZN", repo=None):
    repo = repo or MagicMock()
    out = gate.skip_for_halt(trigger or NEWS, ticker, _tx(holdings if holdings is not None else {"SPY": {"quantity": 1.0}}),
                             repo, "u", engine=eng)
    return out, repo


def test_trigger_ticker_from_field_and_id():
    assert gate.trigger_ticker({"ticker": "JPM"}) == "JPM"
    assert gate.trigger_ticker({"id": "news_AMZN_0.80"}) == "AMZN"
    assert gate.trigger_ticker({"id": "vix_anomaly"}) is None


def test_frozen_unheld_news_is_skipped_and_recorded(engine):
    _state(engine)
    out, repo = _run(engine)
    assert out is True
    kw = repo.log_alert.call_args
    assert kw.args[0] == gate.SKIP_MARKER and kw.kwargs["metadata"]["council_skipped"] == "charter_halt"
    assert kw.kwargs["metadata"]["tickers"] == ["AMZN"]


def test_human_stop_counts_as_halt(engine):
    _state(engine, mode="human_stop", human_stop=True)
    assert _run(engine)[0] is True


def test_not_halted_is_never_skipped(engine):
    _state(engine, mode="dry_run")
    out, repo = _run(engine)
    assert out is False
    repo.log_alert.assert_not_called()


def test_held_ticker_is_not_skipped(engine):
    _state(engine)
    assert _run(engine, holdings={"AMZN": {"quantity": 0.5}})[0] is False


def test_zero_quantity_is_not_held(engine):
    _state(engine)
    assert _run(engine, holdings={"AMZN": {"quantity": 0}})[0] is True


def test_affected_ticker_that_is_held_blocks_the_skip(engine):
    _state(engine)
    trig = dict(NEWS, affected_tickers=["AAPL"])
    assert _run(engine, trigger=trig, holdings={"AAPL": {"quantity": 1.0}})[0] is False


@pytest.mark.parametrize("trigger", [
    {"id": "news_AMZN_0.80", "text": "x", "priority": 0},               # critical priority
    {"id": "news_AMZN_0.80", "text": "x", "level": "CRITICAL"},
    {"id": "price_move_AMZN", "text": "x", "priority": 2},              # not a news trigger
    {"id": "cash_ratio_high", "text": "x"},
])
def test_non_news_or_critical_is_never_skipped(engine, trigger):
    _state(engine)
    assert _run(engine, trigger=trigger)[0] is False


def test_no_ticker_is_not_skipped(engine):
    _state(engine)
    assert _run(engine, ticker=None)[0] is False


def test_unreadable_state_does_not_skip(engine):
    # no charter_state table at all -> read fails -> the council runs as before
    out, repo = _run(create_engine("sqlite:///:memory:"))
    assert out is False
    repo.log_alert.assert_not_called()


def test_unreadable_holdings_does_not_skip(engine):
    _state(engine)
    tx = MagicMock()
    tx.get_holdings_map.side_effect = RuntimeError("db down")
    assert gate.skip_for_halt(NEWS, "AMZN", tx, MagicMock(), "u", engine=engine) is False


def test_alert_history_failure_still_skips_and_warns(engine, caplog):
    _state(engine)
    repo = MagicMock()
    repo.log_alert.side_effect = RuntimeError("boom")
    with caplog.at_level("WARNING"):
        out, _ = _run(engine, repo=repo)
    assert out is True
    assert gate.SKIP_MARKER in caplog.text
