import os
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Global Engine Cache
_db_engines = {}

def get_db_engine(db_path=None) -> Engine:
    """
    Returns a SQLAlchemy Engine.
    Prioritizes DB_URL env var (Postgres).
    Falls back to SQLite if DB_URL is not set.
    """
    global _db_engines
    
    # Check for Postgres Environment Variables
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "postgres")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "portfolio")
    
    # If DB_HOST is set to something other than localhost (e.g. 'postgres' in docker) or we want to force postgres
    # But for local dev defaults might be tricky.
    # Let's check a specific flag or if DB_TYPE is set.
    db_type = os.getenv("DB_TYPE", "sqlite")

    if db_type == "postgres":
        db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    else:
        # SQLite
        if db_path:
            target_path = Path(db_path)
        else:
            target_path = Path("data/portfolio.db")
            
        if not target_path.parent.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
        db_url = f"sqlite:///{target_path}"
        
    if db_url not in _db_engines:
        _db_engines[db_url] = create_engine(db_url)
        
    return _db_engines[db_url]

def get_db_connection(db_path=None):
    """
    Returns a SQLAlchemy Connection object.
    
    NOTE: This is a breaking change from sqlite3.Connection.
    Callers must now use:
    1. conn.execute(text("SELECT..."), params) instead of conn.execute("SELECT...", params)
    2. conn.commit() is native.
    3. Cursors are not used directly in SQLAlchemy Core often, but result proxy is returned.
    """
    engine = get_db_engine(db_path)
    return engine.connect()

def init_db(db_path=None):
    """
    Initialize Database Schema.
    Uses SQLAlchemy to execute raw SQL from init.sql or inline logic.
    For simplicity, we replicate the schema definition here using SQLAlchemy text.
    """
    engine = get_db_engine(db_path)
    
    # Define Schema (Compatible with both generally, but simplistic)
    # Note: In SQLite REAL is float. In Postgres REAL is float4. 
    # TEXT is same.
    
    schema_commands = [
        """CREATE TABLE IF NOT EXISTS transactions (
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
        )""",
        """CREATE TABLE IF NOT EXISTS positions (
            ticker TEXT PRIMARY KEY,
            quantity REAL NOT NULL,
            avg_cost REAL NOT NULL,
            current_price REAL,
            market_value REAL,
            unrealized_pl REAL
        )""",
        """CREATE TABLE IF NOT EXISTS cash_flows (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS recommendations (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            agent TEXT NOT NULL,
            ticker TEXT NOT NULL,
            signal TEXT NOT NULL,
            price_at_signal REAL,
            outcome_score INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS daily_snapshots (
            date TEXT PRIMARY KEY,
            total_nlv REAL,
            cash_balance REAL,
            invested_capital REAL,
            pnl REAL
        )""",
        """CREATE TABLE IF NOT EXISTS scheduler_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            job_name TEXT,
            status TEXT,
            message TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS prompt_history (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            target_agent TEXT,
            reason TEXT,
            original_prompt TEXT,
            new_prompt TEXT,
            diff_content TEXT
        )"""
    ]
    
    with engine.connect() as conn:
        for cmd in schema_commands:
            conn.execute(text(cmd))
        conn.commit()
    
    print(f"Database initialized.")

if __name__ == "__main__":
    init_db()

