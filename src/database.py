import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/portfolio.db")

def get_db_connection(db_path=None):
    """建立並回傳資料庫連線"""
    target_path = Path(db_path) if db_path else DB_PATH
    if not target_path.parent.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    """初始化資料庫 Schema"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Transactions Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        action TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        fees REAL DEFAULT 0,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        source_file TEXT,
        raw_data TEXT
    )
    ''')

    # Positions Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS positions (
        ticker TEXT PRIMARY KEY,
        quantity REAL NOT NULL,
        avg_cost REAL NOT NULL,
        current_price REAL,
        market_value REAL,
        unrealized_pl REAL
    )
    ''')

    # CashFlow Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cash_flows (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        description TEXT
    )
    ''')

    # Recommendations Table (For Refinement Loop)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recommendations (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        agent TEXT NOT NULL,
        ticker TEXT NOT NULL,
        signal TEXT NOT NULL,
        price_at_signal REAL,
        outcome_score INTEGER DEFAULT 0
    )
    ''')

    # Reports Table (For Dashboard & History)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        content TEXT NOT NULL,
        summary TEXT
    )
    ''')

    # 6. Daily Snapshots Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            date TEXT PRIMARY KEY,
            total_nlv REAL,
            cash_balance REAL,
            invested_capital REAL,
            pnl REAL
        )
    ''')
    
    # 7. Scheduler Logs Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduler_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            job_name TEXT,
            status TEXT,
            message TEXT
        )
    ''')
    
    # 8. Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
