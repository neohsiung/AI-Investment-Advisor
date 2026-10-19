"""G8 on real Postgres: the weekly digest is written once per ISO week, and reads the live verdict rows.
G8 在真實 Postgres：週報每個 ISO 週寫一次，並讀取即時判決列。

Watchdog and notifier are injected; evaluate_key is the real one (dry_run run writes the verdict rows it reads).
看門狗與通知以注入提供；evaluate_key 為真實函式（dry_run 寫入的判決列即它所讀取者）。
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from src.services import charter_digest_service as cds
from src.services import parameter_engine as pe
from tests.charter_synth import flat_closes

from .factories import USER_ID

pytestmark = pytest.mark.charter_e2e

KEY = "batch_deploy_min_confidence"
SATURDAY_1 = datetime(2026, 10, 24, 10, 35, tzinfo=timezone.utc)
SATURDAY_2 = datetime(2026, 10, 31, 10, 35, tzinfo=timezone.utc)


def _watchdog(today):
    return {"overall": "OK", "criteria": [], "breaches": []}


def _scalar(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_weekly_digest_once_per_week_with_injected_clock(pg_engine, frozen_clock, notify_sink):
    sent = lambda title, content: notify_sink(content, title=title)
    cds.write_weekly_digest(pg_engine, USER_ID, SATURDAY_1, notify=sent, watchdog=_watchdog)
    cds.write_weekly_digest(pg_engine, USER_ID, SATURDAY_1.replace(hour=11), notify=sent, watchdog=_watchdog)
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'digest'") == 1
    cds.write_weekly_digest(pg_engine, USER_ID, SATURDAY_2, notify=sent, watchdog=_watchdog)
    assert _scalar(pg_engine, "SELECT count(*) FROM charter_events WHERE kind = 'digest'") == 2
    assert len(notify_sink.messages) == 2


def test_digest_reads_live_verdict_rows(pg_engine, frozen_clock, closes_provider, monkeypatch):
    closes_provider.set("SPY", flat_closes(700))
    pe.run_once(USER_ID, pg_engine, frozen_clock.now(), closes_provider=closes_provider)     # dry_run: verdict rows
    d = cds.build_digest(pg_engine, USER_ID, frozen_clock.now(), watchdog=_watchdog)
    row = next(r for r in d["params"] if r["key"] == KEY)
    stored = pg_engine.connect().execute(
        text("SELECT payload_json FROM charter_events WHERE kind = 'verdict' AND key = :k ORDER BY id DESC LIMIT 1"),
        {"k": KEY}).scalar()
    assert row["latest_verdict"] == stored["verdict"]
    assert row["reasons"] == stored["reasons"] and row["reasons"]
    assert d["engine"]["applied_loosenings"] == 0 and d["charter_state"]["mode"] == "dry_run"
