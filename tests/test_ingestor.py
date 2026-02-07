import pytest
import sqlite3
import pandas as pd
from src.data.ingestor import TradeIngestor
from src.data.database import get_db_connection
from sqlalchemy import text
import os

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_portfolio.db"
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()
    return str(db_path)

def test_ingest_simple_csv(test_db, tmp_path):
    # Create dummy CSV
    csv_path = tmp_path / "simple.csv"
    # ... (same)
    df = pd.DataFrame({
        'ticker': ['AAPL', 'GOOGL'],
        'quantity': [10, 5],
        'cost': [150, 2800]
    })
    df.to_csv(csv_path, index=False)

    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_csv(csv_path, broker="simple", user_id="test_user")

    conn = get_db_connection(test_db)
    result = conn.execute(text("SELECT ticker, quantity, price, user_id FROM transactions ORDER BY ticker"))
    rows = result.fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0][0] == 'AAPL' # Access by index or name depending on row type (Tuple in simple cases)
    assert rows[0][3] == 'test_user'



def test_ingest_simple_csv_deposit(test_db, tmp_path):
    df = pd.DataFrame({
        'action': ['DEPOSIT', 'WITHDRAW'],
        'amount': [1000, 500],
        'date': ['2023-01-01', '2023-01-02'],
        'ticker': ['CASH', 'CASH'], # Dummy
        'quantity': [1, 1], # Dummy
        'price': [1000, 500] # Dummy to match amount
    })
    csv_path = tmp_path / "cash.csv"
    df.to_csv(csv_path, index=False)
    
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_csv(csv_path, broker="simple", user_id="u1")
    
    conn = get_db_connection(test_db)
    rows = conn.execute(text("SELECT type, amount FROM cash_flows ORDER BY date")).fetchall()
    conn.close()
    
    assert len(rows) == 2
    assert rows[0][0] == 'DEPOSIT'
    assert rows[0][1] == 1000.0
    assert rows[1][0] == 'WITHDRAWAL'

def test_ingest_robinhood(test_db, tmp_path):
    df = pd.DataFrame({
        'symbol': ['MSFT', 'NVDA'],
        'side': ['buy', 'sell'],
        'quantity': [10, 5],
        'price': [300, 500],
        'date': ['2023-01-01', '2023-01-02'],
        'fees': [1.0, 2.0]
    })
    csv_path = tmp_path / "rh.csv"
    df.to_csv(csv_path, index=False)
    
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_csv(csv_path, broker="robinhood", user_id="u2")
    
    conn = get_db_connection(test_db)
    rows = conn.execute(text("SELECT ticker, action, quantity, price FROM transactions WHERE user_id='u2' ORDER BY ticker")).fetchall()
    conn.close()
    
    assert len(rows) == 2
    # MSFT Buy
    assert rows[0][0] == 'MSFT'
    assert rows[0][1] == 'BUY'
    
    # NVDA Sell
    assert rows[1][0] == 'NVDA'
    assert rows[1][1] == 'SELL'

def test_ingest_ibkr(test_db, tmp_path):
    df = pd.DataFrame({
        'Type': ['Trade', 'Trade'],
        'Symbol': ['AMD', 'INTC'],
        'Date/Time': ['2023-01-01, 10:00:00', '2023-01-02'],
        'Quantity': [10, -5],
        'T. Price': [100, 50],
        'Comm/Fee': [-1.0, -0.5]
    })
    # Add Dividend
    df.loc[2] = ['Dividend', 'AMD', '2023-01-03', 0, 0, 15.0]
    
    csv_path = tmp_path / "ibkr.csv"
    df.to_csv(csv_path, index=False)
    
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_csv(csv_path, broker="ibkr", user_id="u3")
    
    conn = get_db_connection(test_db)
    rows = conn.execute(text("SELECT ticker, action, quantity, amount FROM transactions WHERE user_id='u3' ORDER BY trade_date")).fetchall()
    conn.close()
    
    assert len(rows) == 3
    # AMD Buy
    assert rows[0][0] == 'AMD'
    assert rows[0][1] == 'BUY'
    assert rows[0][2] == 10.0
    
    # INTC Sell
    assert rows[1][0] == 'INTC'
    assert rows[1][1] == 'SELL'
    assert rows[1][2] == 5.0 # Positive quantity stored? Logic says abs(qty)
    
    # AMD Dividend
    assert rows[2][0] == 'AMD'
    assert rows[2][1] == 'DIVIDEND'
    assert rows[2][3] == 15.0 # Amount

def test_ingest_manual_trade(test_db):
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_manual_trade('TSLA', '2023-01-01', 'BUY', 5, 200.0, user_id="test_user")

    conn = get_db_connection(test_db)
    result = conn.execute(text("SELECT ticker, quantity, price, amount, user_id FROM transactions WHERE source_file='manual_entry'"))
    row = result.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 'TSLA'
    assert row[1] == 5.0
    assert row[3] == 1000.0
    assert row[4] == 'test_user'
