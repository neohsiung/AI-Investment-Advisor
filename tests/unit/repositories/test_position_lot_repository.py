"""
Unit tests for PositionLotRepository.

Uses an in-memory SQLite DB to test the full SQL lifecycle without mocking.
"""
import pytest
from sqlalchemy import create_engine, text

from src.repositories.position_lot_repository import AlchemyPositionLotRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_engine():
    """SQLite in-memory engine with position_lots table."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                ticker TEXT,
                trade_date TEXT,
                action TEXT,
                quantity REAL,
                price REAL,
                fees REAL,
                amount REAL,
                leverage REAL DEFAULT 1.0,
                source_file TEXT,
                entry_category TEXT DEFAULT 'trade',
                raw_data TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE position_lots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                open_date TEXT NOT NULL,
                close_date TEXT,
                quantity REAL NOT NULL,
                open_price REAL NOT NULL,
                close_price REAL,
                leverage REAL DEFAULT 1.0,
                is_open INTEGER DEFAULT 1,
                source_tx_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Seed test user
        conn.execute(text("INSERT INTO users (id, email) VALUES ('u1', 'test@test.com')"))
    return engine


@pytest.fixture
def lot_repo(in_memory_engine):
    return AlchemyPositionLotRepository(in_memory_engine)


# ---------------------------------------------------------------------------
# Tests: open_lot / get_open_lots
# ---------------------------------------------------------------------------

def test_open_lot_creates_record(lot_repo):
    lot_id = lot_repo.open_lot(
        user_id="u1",
        ticker="AAPL",
        open_date="2024-01-10",
        quantity=10.0,
        open_price=150.0,
        leverage=1.0,
    )
    assert lot_id is not None

    lots = lot_repo.get_open_lots("u1", ticker="AAPL")
    assert len(lots) == 1
    assert lots[0]["ticker"] == "AAPL"
    assert lots[0]["quantity"] == 10.0
    assert lots[0]["open_price"] == 150.0


def test_get_open_lots_filters_by_ticker(lot_repo):
    lot_repo.open_lot("u1", "AAPL", "2024-01-10", 5.0, 150.0)
    lot_repo.open_lot("u1", "TSLA", "2024-01-11", 3.0, 200.0)

    aapl_lots = lot_repo.get_open_lots("u1", ticker="AAPL")
    assert len(aapl_lots) == 1
    assert aapl_lots[0]["ticker"] == "AAPL"


def test_has_lots_for_user_false_initially(lot_repo):
    assert not lot_repo.has_lots_for_user("u1")


def test_has_lots_for_user_true_after_open(lot_repo):
    lot_repo.open_lot("u1", "AAPL", "2024-01-10", 10.0, 150.0)
    assert lot_repo.has_lots_for_user("u1")


# ---------------------------------------------------------------------------
# Tests: close_lot — full close
# ---------------------------------------------------------------------------

def test_close_lot_full(lot_repo):
    lot_id = lot_repo.open_lot("u1", "AAPL", "2024-01-10", 10.0, 150.0)
    lot_repo.close_lot(lot_id, close_date="2024-06-01", close_price=180.0)

    lots = lot_repo.get_open_lots("u1", ticker="AAPL")
    assert len(lots) == 0  # No open lots remain


def test_close_lot_partial(lot_repo):
    lot_id = lot_repo.open_lot("u1", "GOOG", "2024-01-10", 10.0, 100.0)
    lot_repo.close_lot(lot_id, close_date="2024-06-01", close_price=120.0, quantity_to_close=4.0)

    open_lots = lot_repo.get_open_lots("u1", ticker="GOOG")
    assert len(open_lots) == 1
    assert abs(open_lots[0]["quantity"] - 6.0) < 0.001  # 10 - 4 = 6 remaining


# ---------------------------------------------------------------------------
# Tests: get_avg_cost_map
# ---------------------------------------------------------------------------

def test_get_avg_cost_map_weighted_average(lot_repo):
    # Two lots for AAPL at different prices
    lot_repo.open_lot("u1", "AAPL", "2024-01-10", 10.0, 100.0)  # cost = 1000
    lot_repo.open_lot("u1", "AAPL", "2024-02-10", 10.0, 200.0)  # cost = 2000

    avg_map = lot_repo.get_avg_cost_map("u1")
    # Weighted avg = (1000 + 2000) / 20 = 150
    assert "AAPL" in avg_map
    assert abs(avg_map["AAPL"] - 150.0) < 0.001


def test_get_avg_cost_map_excludes_closed(lot_repo):
    lot_id = lot_repo.open_lot("u1", "TSLA", "2024-01-10", 5.0, 200.0)
    lot_repo.close_lot(lot_id, "2024-06-01", 250.0)

    avg_map = lot_repo.get_avg_cost_map("u1")
    assert "TSLA" not in avg_map  # Closed lot should not appear


# ---------------------------------------------------------------------------
# Tests: backfill_from_transactions
# ---------------------------------------------------------------------------

def test_backfill_from_transactions(lot_repo, in_memory_engine):
    # Seed some transactions
    with in_memory_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO transactions VALUES
              ('tx1', 'u1', 'AAPL', '2024-01-10', 'BUY', 10, 150.0, 0, 1500, 1.0, NULL, 'trade', NULL),
              ('tx2', 'u1', 'AAPL', '2024-03-01', 'SELL', 5, 170.0, 0, 850, 1.0, NULL, 'trade', NULL),
              ('tx3', 'u1', 'GOOG', '2024-02-01', 'BUY', 2, 100.0, 0, 200, 1.0, NULL, 'trade', NULL),
              -- CASH DEPOSIT (capital_flow) - should be skipped
              ('tx4', 'u1', 'CASH', '2024-01-01', 'DEPOSIT', 1, 5000, 0, 5000, 1.0, NULL, 'capital_flow', NULL)
        """))

    count = lot_repo.backfill_from_transactions("u1")

    # Should have 2 open lots (5 AAPL remaining + 2 GOOG); CASH skipped
    assert count == 2

    lots = lot_repo.get_open_lots("u1")
    tickers = {l["ticker"] for l in lots}
    assert "AAPL" in tickers
    assert "GOOG" in tickers
    assert "CASH" not in tickers


def test_backfill_is_idempotent(lot_repo, in_memory_engine):
    with in_memory_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO transactions VALUES
              ('tx1', 'u1', 'AAPL', '2024-01-10', 'BUY', 10, 150.0, 0, 1500, 1.0, NULL, 'trade', NULL)
        """))

    count1 = lot_repo.backfill_from_transactions("u1")
    count2 = lot_repo.backfill_from_transactions("u1")  # Second run

    assert count1 == count2  # Same result both times
    lots = lot_repo.get_open_lots("u1")
    assert len(lots) == 1  # Not duplicated
