import os
import logging
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker, scoped_session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global Engine Cache
_db_engines: Dict[str, Engine] = {}

class BaseRepository:
    """
    Base repository with database-agnostic methods.
    資料庫無關的基礎 Repository。
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.is_sqlite = 'sqlite' in str(engine.url)
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    @property
    def session(self):
        """Returns a scoped session for ORM operations."""
        return self.Session()
    
    def _get_json_extract(self, column: str, path: str) -> str:
        """
        Get database-specific JSON extraction syntax.
        取得資料庫特定的 JSON 提取語法。
        """
        if self.is_sqlite:
            # path like '$.category'
            return f"json_extract({column}, '{path}')"
        else:
            # PostgreSQL JSONB path like 'category'
            json_path = path.replace('$.', '')
            return f"{column}->>'{json_path}'"
    
    def _get_vector_distance(self, column: str, metric: str = "cosine") -> str:
        """
        Get database-specific vector distance calculation.
        取得資料庫特定的向量距離計算。
        """
        if self.is_sqlite:
            # sqlite-vec syntax
            return f"vec_distance_{metric}({column}, :embedding)"
        else:
            # pgvector syntax
            if metric == "cosine":
                return f"{column} <=> :embedding"
            elif metric == "l2":
                return f"{column} <-> :embedding"
            else:
                return f"{column} <=> :embedding"
    
    def _format_vector(self, vector: List[float]) -> Any:
        """
        Format vector for database storage.
        """
        if self.is_sqlite:
            import json
            return json.dumps(vector)
        else:
            return vector

def get_db_engine(db_path=None) -> Engine:
    """
    Returns a SQLAlchemy Engine.
    Strictly uses PostgreSQL. SQLite fallback is disabled unless ALLOW_SQLITE=true.
    """
    global _db_engines

    # 1. Check for explicit DB_URL
    db_url = os.getenv("DB_URL")
    
    # 2. Construct from components (Default to Postgres)
    if not db_url:
        db_user = os.getenv("DB_USER", "postgres")
        db_pass = os.getenv("DB_PASS", "postgres")
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "portfolio")
        db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # 3. Allow SQLite ONLY if explicitly enabled for local dev/testing
    if os.getenv("ALLOW_SQLITE", "false").lower() == "true":
        if "postgresql" not in db_url:
            logger.warning("ALLOW_SQLITE is true, using SQLite fallback.")
            if not db_url.startswith("sqlite"):
                 target_path = Path(db_path) if db_path else Path("data/portfolio.db")
                 if not target_path.parent.exists():
                     target_path.parent.mkdir(parents=True, exist_ok=True)
                 db_url = f"sqlite:///{target_path}"
    elif "sqlite" in db_url:
        raise ConnectionError("SQLite is disabled. Please configure PostgreSQL via DB_URL or DB_USER/PASS/HOST/PORT/NAME.")

    if db_url not in _db_engines:
        connect_args = {'check_same_thread': False} if "sqlite" in db_url else {}
        if "postgresql" in db_url:
            _db_engines[db_url] = create_engine(db_url, pool_size=20, max_overflow=0)
        else:
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
    Initializes the database schema (v4.1.7 Optimized for Postgres).
    Strictly uses UUID, JSONB, NUMERIC, DATE, vector(1536).
    """
    engine = get_db_engine(db_path)
    is_sqlite = 'sqlite' in str(engine.url)
    
    if is_sqlite:
        logger.warning("Initializing on SQLite. Some v4.1+ features may be limited.")

    # Type definitions (Optimized for Postgres)
    pk_type = "TEXT PRIMARY KEY"
    fk_type = "TEXT"
    json_type = "JSONB" if not is_sqlite else "TEXT"
    timestamp_type = "TIMESTAMPTZ" if not is_sqlite else "TEXT"
    date_type = "DATE" if not is_sqlite else "TEXT"
    numeric_type = "NUMERIC(18, 8)" if not is_sqlite else "REAL"
    vector_type = "vector(1536)" if not is_sqlite else "TEXT"

    schema_commands = []
    
    if not is_sqlite:
        schema_commands.append('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        schema_commands.append('CREATE EXTENSION IF NOT EXISTS "vector";')

    # 1. Users table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {pk_type},
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        preferences {json_type} DEFAULT '{{}}',
        metadata {json_type} DEFAULT '{{}}',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        last_login {timestamp_type}
    );
    """)

    # 2. Transactions table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS transactions (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        ticker TEXT NOT NULL,
        trade_date {date_type} NOT NULL,
        action TEXT NOT NULL,
        quantity {numeric_type} NOT NULL,
        price {numeric_type} NOT NULL,
        fees {numeric_type} DEFAULT 0,
        amount {numeric_type} NOT NULL,
        currency TEXT DEFAULT 'USD',
        source_file TEXT,
        raw_data {json_type},
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Memory Embeddings table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS memory_embeddings (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        embedding {vector_type},
        metadata {json_type} DEFAULT '{{}}',
        embedding_model TEXT DEFAULT 'text-embedding-ada-002',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        expires_at {timestamp_type}
    );
    """)

    # 4. Settings table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS settings (
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value {json_type},
        updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, key)
    );
    """)

    # 5. Council Minutes table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS council_minutes (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_id TEXT NOT NULL,
        triggers {json_type} DEFAULT '[]',
        decision TEXT,
        confidence {numeric_type},
        metadata {json_type} DEFAULT '{{}}',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. Event Logs table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS event_logs (
        id {pk_type},
        user_id {fk_type} REFERENCES users(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        severity TEXT,
        title TEXT NOT NULL,
        content TEXT,
        metadata {json_type} DEFAULT '{{}}',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. Reports table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS reports (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding {vector_type},
        metadata {json_type} DEFAULT '{{}}',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        published_at {timestamp_type}
    );
    """)

    # 8. Schema Version table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        description TEXT,
        applied_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 9. User Identities table (v4.0 Identity Resolution)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS user_identities (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        identifier TEXT NOT NULL,
        is_primary INTEGER DEFAULT 0,
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, identifier)
    );
    """)

    # Support tables
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        date {date_type},
        user_id {fk_type},
        total_nlv {numeric_type},
        cash_balance {numeric_type},
        invested_capital {numeric_type},
        pnl {numeric_type},
        total_tnv {numeric_type} DEFAULT 0,
        leverage_ratio {numeric_type} DEFAULT 0,
        PRIMARY KEY (date, user_id)
    );
    """)

    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS cash_flows (
        id {pk_type},
        user_id {fk_type} REFERENCES users(id) ON DELETE CASCADE,
        date {date_type},
        amount {numeric_type},
        type TEXT,
        description TEXT
    );
    """)

    # Risk Keywords table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS risk_keywords (
        id {pk_type},
        keyword TEXT NOT NULL,
        weight {numeric_type} DEFAULT 0.5,
        category TEXT DEFAULT 'custom',
        hit_count INTEGER DEFAULT 0,
        last_hit_date {date_type},
        is_active INTEGER DEFAULT 1,
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Channel Verifications table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS channel_verifications (
        id {pk_type},
        user_id {fk_type},
        channel TEXT,
        channel_user_id TEXT,
        code TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        expires_at {timestamp_type},
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    with engine.connect() as conn:
        for cmd in schema_commands:
            try:
                conn.execute(text(cmd))
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Error executing schema command: {e}")
        
        # v4.1.7: Post-deployment strict migrations (UUID focus)
        if not is_sqlite:
            # Add Unique Index for UPSERT on daily_snapshots if missing
            try:
                check_idx = text("SELECT indexname FROM pg_indexes WHERE tablename = 'daily_snapshots' AND indexdef LIKE '%(date, user_id)%'")
                if not conn.execute(check_idx).fetchone():
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_snapshots_upsert ON daily_snapshots(date, user_id)"))
            except Exception as e:
                logger.warning(f"Failed to create unique index: {e}")

        conn.commit()
    
    logger.info(f"Database initialized with v4.1.7 optimized Postgres schema.")

if __name__ == "__main__":
    init_db()
