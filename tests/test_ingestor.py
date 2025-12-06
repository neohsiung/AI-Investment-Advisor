import pytest
import sqlite3
import pandas as pd
from src.ingestor import TradeIngestor
from src.database import get_db_connection
from sqlalchemy import text
import os

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_portfolio.db"
    # Use SQLAlchemy to init schema to match app behavior
    # Or keep using sqlite3 if we want to valid raw file.
    # Let's use generic init logic.
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
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
    ingestor.ingest_csv(csv_path, broker="simple")
    
    conn = get_db_connection(test_db)
    result = conn.execute(text("SELECT ticker, quantity, price FROM transactions ORDER BY ticker"))
    rows = result.fetchall()
    conn.close()
    
    assert len(rows) == 2
    assert rows[0][0] == 'AAPL' # Access by index or name depending on row type (Tuple in simple cases)

def test_ingest_manual_trade(test_db):
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_manual_trade('TSLA', '2023-01-01', 'BUY', 5, 200.0)
    
    # Use SQLAlchemy to verify
    conn = get_db_connection(test_db)
    result = conn.execute(text("SELECT ticker, quantity, price, amount FROM transactions"))
    row = result.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == 'TSLA'
    assert row[1] == 5.0
    assert row[3] == 1000.0
