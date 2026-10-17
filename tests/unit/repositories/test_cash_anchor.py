"""Single cash-anchor row: local ledger cash converges to broker cash and is idempotent."""
import pytest
from sqlalchemy import create_engine, text

from src.repositories.transaction_repository import (
    AlchemyTransactionRepository, ENTRY_CATEGORY_CAPITAL_FLOW, ENTRY_CATEGORY_SYNC_ADJUSTMENT, ENTRY_CATEGORY_TRADE,
)


@pytest.fixture
def repo():
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("""CREATE TABLE transactions (id TEXT, user_id TEXT, ticker TEXT, trade_date TEXT, action TEXT,
            quantity REAL, price REAL, fees REAL, amount REAL, leverage REAL, source_file TEXT, entry_category TEXT,
            raw_data TEXT, currency TEXT, created_at TEXT, updated_at TEXT)"""))
    r = AlchemyTransactionRepository.__new__(AlchemyTransactionRepository)
    r.engine = eng
    return r


def _seed(repo):
    repo.add("u", "CASH", "2026-01-01", "DEPOSIT", 1, 1000, 0, entry_category=ENTRY_CATEGORY_CAPITAL_FLOW, amount=1000)
    repo.add("u", "AAPL", "2026-01-02", "BUY", 1, 100, 0, entry_category=ENTRY_CATEGORY_TRADE, amount=100)
    # legacy per-day CASH sync rows (still counted by get_cash_flow_sum)
    repo.add("u", "CASH", "2026-01-03", "DEPOSIT", 1, 500, 0, entry_category=ENTRY_CATEGORY_SYNC_ADJUSTMENT,
             amount=500, source_file="ETORO_SYNC")


def test_anchor_converges_and_is_idempotent(repo):
    _seed(repo)
    assert repo.get_cash_balance("u") == pytest.approx(1400.0)      # 1000 - 100 + 500 legacy sync
    repo.set_cash_anchor("u", 650.0)
    assert repo.get_cash_balance("u") == pytest.approx(650.0)
    repo.set_cash_anchor("u", 650.0)                                  # no compounding
    assert repo.get_cash_balance("u") == pytest.approx(650.0)
    repo.set_cash_anchor("u", 1200.0)                                 # moves up too
    assert repo.get_cash_balance("u") == pytest.approx(1200.0)
    with repo.engine.connect() as c:
        n = c.execute(text("select count(*) from transactions where source_file='LEDGER_ANCHOR'")).scalar()
    assert n == 1


def test_base_excludes_anchor_and_trades_move_balance(repo):
    _seed(repo)
    repo.set_cash_anchor("u", 650.0)
    assert repo.get_cash_balance("u", None, include_anchor=False) == pytest.approx(1400.0)
    repo.add("u", "MSFT", "2026-01-04", "BUY", 1, 50, 0, entry_category=ENTRY_CATEGORY_TRADE, amount=50)
    assert repo.get_cash_balance("u") == pytest.approx(600.0)         # anchor offset persists, new trade applies


def test_reconcile_cash_balance_uses_anchor(repo):
    _seed(repo)
    repo.reconcile_cash_balance("u", 777.0, "etoro")
    assert repo.get_cash_balance("u") == pytest.approx(777.0)


def test_has_matching_buy_sees_system_order_but_not_backfill_rows(repo):
    repo.add("u", "MSFT", "2026-10-16 13:37:16", "BUY", 0.18519, 540.0, 0, entry_category=ENTRY_CATEGORY_TRADE,
             amount=100.0, source_file="eToro")
    assert repo.has_matching_buy("u", "MSFT", 0.18520, "2026-10-16")             # within 1%
    assert not repo.has_matching_buy("u", "MSFT", 0.50, "2026-10-16")            # different size
    assert not repo.has_matching_buy("u", "MSFT", 0.18519, "2026-10-15")         # different day
    repo.add("u", "AAPL", "2026-10-16", "BUY", 0.29, 343.0, 0, entry_category=ENTRY_CATEGORY_SYNC_ADJUSTMENT,
             amount=100.0, source_file="etoro_pos_123")
    assert not repo.has_matching_buy("u", "AAPL", 0.29, "2026-10-16")            # a backfill row is not a system order
