import os
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
        # SQLite specific args for concurrency
        connect_args = {'check_same_thread': False} if "sqlite" in db_url else {}
        _db_engines[db_url] = create_engine(db_url, connect_args=connect_args)

    return _db_engines[db_url]

def get_db_connection(db_path=None):
    """
    Returns a SQLAlchemy Connection object.
    """
    engine = get_db_engine(db_path)
    return engine.connect()

def init_db(db_path=None):
    """
    Initialize Database Schema v3.
    """
    engine = get_db_engine(db_path)

    # Detect DB Type from Engine Dialect
    is_sqlite = 'sqlite' in str(engine.url)
    embedding_type = "TEXT" if is_sqlite else "vector(1536)"

    schema_commands = []
    
    # --- Extensions ---
    if not is_sqlite:
        schema_commands.append("CREATE EXTENSION IF NOT EXISTS vector;")
        
    # --- Tables ---
    schema_commands.extend([
        # --- Core User & Trans (v1) ---
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
            total_tnv REAL DEFAULT 0,
            leverage_ratio REAL DEFAULT 0,
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
        )""",
        """CREATE TABLE IF NOT EXISTS event_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            source TEXT,        -- e.g., 'webhook/news', 'process/daily_scan'
            level TEXT,         -- 'INFO', 'WARNING', 'CRITICAL'
            title TEXT,
            content TEXT,
            metadata TEXT,      -- JSON string for extra fields
            processed_by TEXT   -- Which component handled it
        )""",
        """CREATE TABLE IF NOT EXISTS manual_inputs (
            id TEXT PRIMARY KEY,
            date TEXT,
            user_id TEXT,
            input_type TEXT,    -- 'PDF', 'TEXT', 'URL'
            content TEXT,
            status TEXT,        -- 'PENDING', 'PROCESSED', 'FAILED'
            assigned_agent TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS agent_knowledge (
            id TEXT PRIMARY KEY,
            agent_name TEXT,    -- e.g., 'Momentum'
            topic TEXT,
            summary TEXT,
            source_ref TEXT,
            timestamp TEXT,
            ttl_date TEXT,      -- For Data Lifecycle (Pruning)
            vector_id TEXT      -- If we add vector DB later
        )""",
        """CREATE TABLE IF NOT EXISTS agent_states (
            id TEXT PRIMARY KEY,
            agent_name TEXT,
            last_input_hash TEXT,
            last_run_time TEXT,
            last_output TEXT,
            FOREIGN KEY(agent_name) REFERENCES settings(key) -- loose fk
        )""",
        """CREATE TABLE IF NOT EXISTS position_snapshots (
             id TEXT PRIMARY KEY,
             date TEXT,
             user_id TEXT,
             ticker TEXT,
             shares REAL,
             avg_cost REAL,
             market_price REAL,
             market_value REAL,
             unrealized_pl REAL,
             FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        # --- New Tables for v3.4 (Sentinel & Council) ---
        """CREATE TABLE IF NOT EXISTS memory_embeddings (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            timestamp TEXT,
            category TEXT,      -- 'user_profile', 'market_event', 'news'
            content TEXT,
            embedding vector(1536),
            metadata TEXT       -- JSON string for extra fields
        )""",
        """CREATE TABLE IF NOT EXISTS council_minutes (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            topic TEXT,
            participants TEXT,  -- JSON list of agent names
            consensus_decision TEXT,
            full_transcript TEXT,
            embedding vector(1536) -- Embedding of the consensus/topic for retrieval
        )""",
        # Dynamic Table Definition for Vector Support (Legacy/Compat)
        f'''CREATE TABLE IF NOT EXISTS agent_feedback (
            id TEXT PRIMARY KEY,
            agent_name TEXT,
            context_embedding {embedding_type}, 
            context_text TEXT,
            response_text TEXT,
            outcome_score REAL,
            timestamp TEXT
        )''',
        """CREATE TABLE IF NOT EXISTS agent_reviews (
            id TEXT PRIMARY KEY,
            reviewer TEXT,
            reviewee TEXT,
            score INTEGER,
            comment TEXT,
            context_hash TEXT,
            timestamp TEXT
        )"""
    ])

    with engine.connect() as conn:
        for cmd in schema_commands:
            conn.execute(text(cmd))
        
        # Migration: Add new columns to daily_snapshots if missing (SQLite specific)
        try:
             # Check if column exists by trying to select it
             conn.execute(text("SELECT total_tnv FROM daily_snapshots LIMIT 1"))
        except Exception:
             print("Migrating daily_snapshots: Adding total_tnv and leverage_ratio columns...")
             try:
                # Add columns one by one
                conn.execute(text("ALTER TABLE daily_snapshots ADD COLUMN total_tnv REAL DEFAULT 0"))
                conn.execute(text("ALTER TABLE daily_snapshots ADD COLUMN leverage_ratio REAL DEFAULT 0"))
             except Exception as e:
                print(f"Migration failed details: {e}")

        # Migration for agent_states
        try:
             conn.execute(text("SELECT last_output FROM agent_states LIMIT 1"))
        except Exception:
             print("Migrating agent_states: Adding last_output column...")
             try:
                conn.execute(text("ALTER TABLE agent_states ADD COLUMN last_output TEXT"))
             except Exception as e:
                pass

        # Migration for agent_feedback (context_text)
        try:
             conn.execute(text("SELECT context_text FROM agent_feedback LIMIT 1"))
        except Exception:
             print("Migrating agent_feedback: Adding context_text column...")
             try:
                conn.execute(text("ALTER TABLE agent_feedback ADD COLUMN context_text TEXT"))
             except Exception as e:
                print(f"Migration agent_feedback failed: {e}")

        # Migration for reports (report_type)
        try:
             conn.execute(text("SELECT report_type FROM reports LIMIT 1"))
        except Exception:
             print("Migrating reports: Adding report_type column...")
             try:
                conn.execute(text("ALTER TABLE reports ADD COLUMN report_type TEXT DEFAULT 'generic'"))
             except Exception as e:
                print(f"Migration reports failed: {e}")

        conn.commit()

    # print(f"Database initialized with v3 schema (Adapter: {'SQLite' if is_sqlite else 'Postgres'}).")

if __name__ == "__main__":
    init_db()
