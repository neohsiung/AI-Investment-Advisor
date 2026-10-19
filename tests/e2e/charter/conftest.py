"""Charter E2E harness (E0): throwaway Postgres at alembic head, per-test truncate, frozen clock, injected sinks.
章程 E2E harness：一次性 Postgres 升到 head、每測試 TRUNCATE、凍結時鐘、注入式通知與行情。"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from .factories import (TRUNCATE_TABLES, ClosesProvider, FrozenClock, NotifySink, resolve_pg_url,
                        set_charter_state)

REPO = Path(__file__).resolve().parents[3]


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/e2e/charter" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(pytest.mark.charter_e2e)


@pytest.fixture(scope="session")
def pg_url():
    url = resolve_pg_url()
    if url is None:
        msg = ("no Postgres for charter_e2e: set CHARTER_E2E_PG_URL (database 'portfolio' or 'charter_e2e*' on "
               "localhost) or run under GitHub Actions with DB_* set")
        if os.getenv("CHARTER_E2E_REQUIRE_PG") or os.getenv("CI"):
            pytest.fail(msg)
        pytest.skip(msg)
    return url


@pytest.fixture(scope="session")
def _migrated_engine(pg_url):
    """Upgrade to head unless already there. tests/conftest.py forces DB_URL to sqlite, so point it at Postgres for
    the alembic run only. / tests/conftest.py 把 DB_URL 強制設成 sqlite，所以只在 alembic 執行期間改指 Postgres。"""
    engine = create_engine(pg_url)
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "alembic"))
    head = set(ScriptDirectory.from_config(cfg).get_heads())
    with engine.connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    if current != head:
        mp = pytest.MonkeyPatch()
        mp.setenv("DB_URL", pg_url)
        flags = {n: lg.disabled for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
        try:
            command.upgrade(cfg, "head")
        finally:
            mp.undo()
            for n, disabled in flags.items():      # alembic's fileConfig disables existing loggers / 還原被停用的 logger
                logging.getLogger(n).disabled = disabled
    yield engine
    engine.dispose()


@pytest.fixture
def pg_engine(_migrated_engine):
    with _migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    set_charter_state(_migrated_engine, "dry_run", reason="charter_e2e reseed")
    return _migrated_engine


@pytest.fixture
def frozen_clock():
    clock = FrozenClock(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)).start()
    try:
        yield clock
    finally:
        clock.stop()


@pytest.fixture
def notify_sink():
    return NotifySink()


@pytest.fixture
def closes_provider():
    return ClosesProvider()
