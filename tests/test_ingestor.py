import pytest
import sqlite3
import pandas as pd
from src.ingestor import TradeIngestor
import os

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_portfolio.db"
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
    df = pd.DataFrame({
        'ticker': ['AAPL', 'GOOGL'],
        'quantity': [10, 5],
        'cost': [150, 2800]
    })
    df.to_csv(csv_path, index=False)
    
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_csv(csv_path, broker="simple")
    
    conn = sqlite3.connect(test_db)
    rows = conn.execute("SELECT ticker, quantity, price FROM transactions ORDER BY ticker").fetchall()
    conn.close()
    
    assert len(rows) == 2
    assert rows[0] == ('AAPL', 10.0, 150.0)
    assert rows[1] == ('GOOGL', 5.0, 2800.0)

def test_ingest_manual_trade(test_db):
    ingestor = TradeIngestor(db_path=test_db)
    ingestor.ingest_manual_trade('TSLA', '2023-01-01', 'BUY', 5, 200.0)
    
    conn = sqlite3.connect(test_db)
    row = conn.execute("SELECT ticker, quantity, price, amount FROM transactions").fetchone()
    conn.close()
    
    assert row == ('TSLA', 5.0, 200.0, 1000.0)
