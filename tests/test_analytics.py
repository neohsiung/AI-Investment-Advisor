import pytest
import sqlite3
import pandas as pd
from src.analytics import LeverageCalculator, ROIEngine, SnapshotRecorder
from src.data.database import init_db

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_portfolio.db"

    # Initialize DB schema
    conn = sqlite3.connect(db_path)
    # Recreate schema manually or import init_db logic if it accepts db_path
    # Since init_db in src.database might use default path, we'll manually create tables needed
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            ticker TEXT,
            trade_date TEXT,
            action TEXT,
            quantity REAL,
            price REAL,
            fees REAL,
            amount REAL,
            source_file TEXT,
            raw_data TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cash_flows (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT,
            amount REAL,
            type TEXT,
            description TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            date TEXT,
            user_id TEXT,
            total_nlv REAL,
            cash_balance REAL,
            invested_capital REAL,
            pnl REAL,
            total_tnv REAL,
            leverage_ratio REAL,
            PRIMARY KEY (date, user_id)
        )
    ''')
    conn.commit()
    conn.close()
    return str(db_path)

def test_leverage_calculator(test_db):
    conn = sqlite3.connect(test_db)
    # Deposit 10000
    conn.execute("INSERT INTO cash_flows (id, user_id, date, amount, type) VALUES ('1', 'test_user', '2023-01-01', 10000, 'DEPOSIT')")
    # Buy AAPL: 10 shares @ 150 (Cost 1500)
    conn.execute("INSERT INTO transactions (id, user_id, ticker, action, quantity, price, fees, amount) VALUES ('t1', 'test_user', 'AAPL', 'BUY', 10, 150, 0, 1500)")
    conn.commit()
    conn.close()

    calc = LeverageCalculator(db_path=test_db)
    current_prices = {'AAPL': 160.0} # Price goes up

    metrics = calc.calculate_metrics(current_prices, user_id='test_user')

    # TNV = 10 * 160 = 1600
    assert metrics['tnv'] == 1600.0

    # Cash Balance = 10000 - 1500 = 8500
    assert metrics['cash_balance'] == 8500.0

    # NLV = 8500 + 1600 = 10100
    assert metrics['nlv'] == 10100.0

    # Leverage = 1600 / 10100 ~= 0.158
    assert 0.15 < metrics['leverage_ratio'] < 0.16

def test_roi_engine(test_db):
    conn = sqlite3.connect(test_db)
    # Deposit 10000
    conn.execute("INSERT INTO cash_flows (id, user_id, date, amount, type) VALUES ('1', 'test_user', '2023-01-01', 10000, 'DEPOSIT')")
    conn.commit()
    conn.close()

    engine = ROIEngine(db_path=test_db)

    # Case 1: No profit
    roi = engine.calculate_roi(nlv=10000, user_id='test_user')
    assert roi == 0.0

    # Case 2: Profit 1000
    roi = engine.calculate_roi(nlv=11000, user_id='test_user')
    assert roi == 10.0 # (11000 - 10000) / 10000 * 100

def test_snapshot_recorder(test_db):
    conn = sqlite3.connect(test_db)
    conn.execute("INSERT INTO cash_flows (id, user_id, date, amount, type) VALUES ('1', 'test_user', '2023-01-01', 10000, 'DEPOSIT')")
    conn.commit()
    conn.close()

    recorder = SnapshotRecorder(db_path=test_db)
    recorder.record_daily_snapshot(nlv=10500, cash_balance=5000, user_id='test_user')

    conn = sqlite3.connect(test_db)
    row = conn.execute("SELECT * FROM daily_snapshots").fetchone()
    conn.close()

    assert row is not None
    # date, user_id, nlv, cash, invested, pnl
    # Note: Using SELECT * order depends on schema creation.
    # Schema: date, user_id, total_nlv, cash_balance, invested_capital, pnl
    assert row[1] == 'test_user'
    assert row[2] == 10500
    assert row[3] == 5000
    assert row[4] == 10000 # Invested
    assert row[5] == 500 # PnL
