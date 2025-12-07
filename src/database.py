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
        """CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            created_at TEXT,
            last_login TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            ticker TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            fees REAL DEFAULT 0,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            source_file TEXT,
            raw_data TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        # Positions: Re-created with Composite PK (user_id, ticker)
        """CREATE TABLE IF NOT EXISTS positions (
            user_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quantity REAL NOT NULL,
            avg_cost REAL NOT NULL,
            current_price REAL,
            market_value REAL,
            unrealized_pl REAL,
            PRIMARY KEY (user_id, ticker),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS cash_flows (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS recommendations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT NOT NULL,
            agent TEXT NOT NULL,
            ticker TEXT NOT NULL,
            signal TEXT NOT NULL,
            price_at_signal REAL,
            outcome_score INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS daily_snapshots (
            date TEXT,
            user_id TEXT,
            total_nlv REAL,
            cash_balance REAL,
            invested_capital REAL,
            pnl REAL,
            PRIMARY KEY (date, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS scheduler_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            job_name TEXT,
            status TEXT,
            message TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT,
            user_id TEXT,
            value TEXT,
            PRIMARY KEY (key, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS prompt_history (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            timestamp TEXT,
            target_agent TEXT,
            reason TEXT,
            original_prompt TEXT,
            new_prompt TEXT,
            diff_content TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )"""
    ]
    
    with engine.connect() as conn:
        # 1. Create tables if not exist
        for cmd in schema_commands:
            conn.execute(text(cmd))
            
        # 2. Migration: Check and add columns if missing (SQLite limitation: easy ADD COLUMN)
        # We need to check each table for 'user_id' column
        tables_to_check = ['transactions', 'cash_flows', 'recommendations', 'reports', 'prompt_history']
        
        for table in tables_to_check:
            try:
                # Check if column exists (pragmatic way for SQLite)
                # In standard SQL, we query information_schema, but for simplicity/compat:
                try:
                    conn.execute(text(f"SELECT user_id FROM {table} LIMIT 1")) # nosec B608
                except Exception:
                    # Column likely missing
                    print(f"Migrating {table}: Adding user_id column...")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id TEXT")) # nosec B608
            except Exception as e:
                print(f"Migration check failed for {table}: {e}")

        # 3. Special Case: Schema Changes that require Recreation
        # Strategy: Rename old table, create new, copy data (with default user_id), drop old.
        
        # Default user configuration
        # 使用者可以透過環境變數設定「現有資料」要歸屬給誰
        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        default_user_id = admin_email  # 簡單起見，直接用 Email 當 ID，或保持 'default_user' 但 Email 設定正確
        # 為了避免 ID 衝突或特殊字元，我們還是用 'default_user' 作為內部 ID，但在 users 表中紀錄正確 Email
        # 當使用者登入時 (Google Auth)，我們需要邏輯將 'default_user' 的資料轉移給他，或者
        # 簡單一點：直接把 default_user_id 設為該 Email (假設 Email 不會變)
        # 這樣登入後直接用 Email 查詢就能看到舊資料
        
        target_user_id = admin_email
        
        # Ensure default user exists
        conn.execute(text("INSERT OR IGNORE INTO users (id, email, name) VALUES (:id, :email, :name)"), 
                     {"id": target_user_id, "email": admin_email, "name": "Admin User"})

        special_tables = ['positions', 'daily_snapshots', 'settings']
        for table in special_tables:
            try:
                # Check if user_id exists
                try:
                    conn.execute(text(f"SELECT user_id FROM {table} LIMIT 1")) # nosec B608
                except Exception:
                    # Need migration
                    print(f"Migrating {table}: Recreating with Composite PK for {target_user_id}...")
                    conn.execute(text(f"ALTER TABLE {table} RENAME TO {table}_old")) # nosec B608
                    
                    # Create new table
                    create_stmt = next(cmd for cmd in schema_commands if f"TABLE IF NOT EXISTS {table}" in cmd)
                    conn.execute(text(create_stmt))
                    
                    # Copy Data
                    if table == 'positions':
                        cols = "ticker, quantity, avg_cost, current_price, market_value, unrealized_pl"
                        conn.execute(text(f"INSERT INTO {table} (user_id, {cols}) SELECT :uid, {cols} FROM {table}_old"), {"uid": target_user_id}) # nosec B608
                    elif table == 'daily_snapshots':
                        cols = "date, total_nlv, cash_balance, invested_capital, pnl"
                        conn.execute(text(f"INSERT INTO {table} (date, user_id, {cols}) SELECT date, :uid, {cols} FROM {table}_old"), {"uid": target_user_id}) # nosec B608
                    elif table == 'settings':
                        cols = "key, value"
                        conn.execute(text(f"INSERT INTO {table} (key, user_id, value) SELECT key, :uid, value FROM {table}_old"), {"uid": target_user_id}) # nosec B608
                    
                    # Drop old
                    conn.execute(text(f"DROP TABLE {table}_old")) # nosec B608
            except Exception as e:
                print(f"Special migration failed for {table}: {e}")

        conn.commit()
    
    print(f"Database initialized and migrated.")

if __name__ == "__main__":
    init_db()

