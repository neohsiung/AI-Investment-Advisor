import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# v8.0 Global Async Engine Cache
_async_db_engines: Dict[str, AsyncEngine] = {}

# Global Engine Cache
_db_engines: Dict[str, Engine] = {}

# Global Session Registries (one per engine) to prevent leaks
_session_registries: Dict[Engine, Any] = {}

# Global Initialization Registry to track which databases have been initialized
_db_initialized: set = set()

class BaseRepository:
    def __init__(self, engine: Engine):
        self.engine = engine
        
        global _session_registries
        if engine not in _session_registries:
            # v4.2.6: Use a single shared scoped_session registry per engine
            # to ensure thread-local sessions are shared across repository instances.
            factory = sessionmaker(bind=self.engine)
            _session_registries[engine] = scoped_session(factory)
        
        self.Session = _session_registries[engine]

    @property
    def session(self):
        """Returns a scoped session for ORM operations."""
        return self.Session()
        
    def close_session(self):
        """Closes and removes the current scoped session."""
        self.Session.remove()
    
    def _get_json_extract(self, column: str, path: str) -> str:
        """
        Get PostgreSQL JSONB extraction syntax.
        取得 PostgreSQL JSONB 提取語法。
        """
        # PostgreSQL JSONB path like 'category'
        json_path = path.replace('$.', '')
        return f"{column}->>'{json_path}'"
    
    def _get_vector_distance(self, column: str, metric: str = "cosine") -> str:
        """
        Get PostgreSQL pgvector distance calculation.
        取得 PostgreSQL pgvector 向量距離計算。
        """
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
        return vector

def get_db_engine(db_path: str = None, use_null_pool: bool = False) -> Engine:
    """
    Returns a SQLAlchemy Engine with optimized pooling.
    v7.3: Added use_null_pool support for multi-process isolation (Celery).
    """
    global _db_engines

    # v7.3: Detect if we are running inside a Celery worker to enforce safe pooling
    is_celery = os.getenv("IS_CELERY_WORKER", "false").lower() == "true"
    should_use_null_pool = use_null_pool or is_celery

    # 1. Check for explicit DB_URL
    db_url = os.getenv("DB_URL")
    
    # v4.2.1: Allow SQLite *only* if db_path is explicitly provided (Test Isolation)
    if db_path:
        db_url = f"sqlite:///{db_path}"
    
    # 2. Construct from components (Default to Postgres)
    if not db_url:
        db_user = os.getenv("DB_USER", "postgres")
        db_pass = os.getenv("DB_PASS", "postgres")
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "portfolio")
        
        if not db_host:
            db_host = "postgres"
            if "PYTEST_CURRENT_TEST" not in os.environ:
                 logger.warning(f"DB_HOST not set. Defaulting to '{db_host}'.")
        
        db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # Cache key includes pool type to prevent sharing incompatible engines
    cache_key = f"{db_url}_nullpool_{should_use_null_pool}"

    if cache_key not in _db_engines:
        if "postgres" in db_url:
            from sqlalchemy.pool import NullPool
            if should_use_null_pool:
                logger.info(f"Using PostgreSQL engine with NullPool for process isolation.")
                engine = create_engine(db_url, poolclass=NullPool)
            else:
                # v19.1: Increased pooling for high-concurrency [Phase 19]
                engine = create_engine(
                    db_url, 
                    pool_size=20, 
                    max_overflow=50,
                    pool_timeout=30,
                    pool_recycle=3600
                )
                logger.info(f"Using PostgreSQL engine with QueuePool (size=20, overflow=50).")
        else:
            from sqlalchemy.pool import StaticPool
            if "memory" in db_url.lower():
                engine = create_engine(
                    db_url, 
                    poolclass=StaticPool, 
                    connect_args={'check_same_thread': False}
                )
            else:
                engine = create_engine(db_url)
            
        # Optional: Instrument the engine for OpenTelemetry
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument(engine=engine)
        except (ImportError, Exception):
            pass
            
        _db_engines[cache_key] = engine

    return _db_engines[cache_key]

def get_async_db_engine(db_path: str = None) -> AsyncEngine:
    """
    Returns a SQLAlchemy AsyncEngine with optimized settings.
    v8.0: Initial implementation for high-concurrency async I/O.
    """
    global _async_db_engines

    # 1. Resolve DB URL
    db_url = os.getenv("DB_URL")
    if db_path:
        db_url = f"sqlite+aiosqlite:///{db_path}"
    
    if not db_url:
        db_user = os.getenv("DB_USER", "postgres")
        db_pass = os.getenv("DB_PASS", "postgres")
        db_host = os.getenv("DB_HOST", "postgres")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "portfolio")
        db_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    else:
        # v8.0: Swap driver for async compatibility
        if "postgresql+psycopg2" in db_url:
            db_url = db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
        elif "sqlite" in db_url and "aiosqlite" not in db_url:
            db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")

    if db_url not in _async_db_engines:
        if "postgresql" in db_url:
            # v19.1: Increased async pooling for high-concurrency [Phase 19]
            engine = create_async_engine(
                db_url,
                pool_size=20,
                max_overflow=50,
                pool_recycle=3600,
                pool_timeout=30
            )
            logger.info(f"Using PostgreSQL AsyncEngine: {db_url.split('@')[-1]}")
        else:
            engine = create_async_engine(db_url)
            
        _async_db_engines[db_url] = engine

    return _async_db_engines[db_url]

class AsyncBaseRepository:
    """
    Base class for repositories using non-blocking async DB operations.
    v8.0: Core component for Phase 8 performance upgrade.
    """
    def __init__(self, engine: Optional[AsyncEngine] = None):
        self.engine = engine or get_async_db_engine()
        self.session_factory = async_sessionmaker(
            bind=self.engine, 
            expire_on_commit=False,
            class_=AsyncSession
        )

    async def get_session(self) -> AsyncSession:
        """Returns a new async session."""
        return self.session_factory()

def get_db_connection(db_path=None):
    """
    Returns a SQLAlchemy Connection object.
    """
    engine = get_db_engine(db_path)
    return engine.connect()

def init_db(db_path=None, force=False, engine=None):
    """
    Initializes the database schema (v4.1.7 Optimized for Postgres).
    Strictly uses UUID, JSONB, NUMERIC, DATE, vector(1536).
    """
    global _db_initialized
    db_url = os.getenv("DB_URL")
    if db_path:
        db_url = f"sqlite:///{db_path}"
    elif not db_url:
        db_user = os.getenv("DB_USER", "postgres")
        db_pass = os.getenv("DB_PASS", "postgres")
        db_host = os.getenv("DB_HOST", "postgres")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "portfolio")
        db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    if engine is None:
        engine = get_db_engine(db_path)
    
    # v5.0.1: If engine is provided or it's an in-memory test DB,
    # we should check initialization against the engine object itself or allow re-init.
    db_url = str(engine.url) if engine else db_url
    
    if db_url in _db_initialized and not force and ":memory:" not in db_url:
        return
    
    is_sqlite = engine.dialect.name == "sqlite"
    
    # Type mapping (v4.2.1: Optimized for Postgres with SQLite fallback for tests)
    pk_type = "TEXT PRIMARY KEY"
    fk_type = "TEXT"
    json_type = "JSONB" if not is_sqlite else "JSON"
    timestamp_type = "TIMESTAMPTZ" if not is_sqlite else "TIMESTAMP"
    date_type = "DATE"
    numeric_type = "NUMERIC(18, 8)"
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
        user_id {fk_type} NOT NULL {"REFERENCES users(id) ON DELETE CASCADE" if not is_sqlite else ""},
        session_id TEXT NOT NULL,
        topic TEXT,
        participants TEXT,
        consensus TEXT,
        transcript TEXT,
        embedding {vector_type},
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

    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        date {date_type},
        user_id {fk_type},
        account_id TEXT DEFAULT '',
        total_nlv {numeric_type},
        cash_balance {numeric_type},
        invested_capital {numeric_type},
        pnl {numeric_type},
        total_tnv {numeric_type} DEFAULT 0,
        leverage_ratio {numeric_type} DEFAULT 0,
        conviction_level {numeric_type} DEFAULT 0,
        time_horizon TEXT,
        PRIMARY KEY (date, user_id, account_id)
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
        keyword TEXT NOT NULL UNIQUE,
        weight {numeric_type} DEFAULT 0.5,
        category TEXT DEFAULT 'custom',
        hit_count INTEGER DEFAULT 0,
        last_hit_date {date_type},
        is_active INTEGER DEFAULT 1,
        source TEXT DEFAULT 'seed',
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

    # 10. Web Push Subscriptions table [Phase 20]
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS web_push_subscriptions (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        subscription_json {json_type} NOT NULL,
        device_info {json_type} DEFAULT '{{}}',
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 10. Agent Feedback (Experience Training)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS agent_feedback (
        id {pk_type},
        agent_name TEXT NOT NULL,
        context_embedding {vector_type},
        context_text TEXT,
        response_text TEXT,
        signal TEXT,
        outcome_score {numeric_type},
        timestamp {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 11. Agent Reviews (HR 360)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS agent_reviews (
        id {pk_type},
        reviewer TEXT NOT NULL,
        reviewee TEXT NOT NULL,
        score INTEGER NOT NULL,
        comment TEXT,
        context_hash TEXT,
        timestamp {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 12. Recommendations table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS recommendations (
        id {pk_type},
        user_id {fk_type} NOT NULL {"REFERENCES users(id) ON DELETE CASCADE" if not is_sqlite else ""},
        date {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        agent TEXT NOT NULL,
        ticker TEXT NOT NULL,
        signal TEXT NOT NULL,
        price_at_signal {numeric_type},
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 13. Scheduler Logs table
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS scheduler_logs (
        id {pk_type},
        timestamp {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        job_name TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT,
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 14. Investment Skills table (Daily Skill Learning System)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS investment_skills (
        id {pk_type},
        user_id {fk_type} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        timeframe TEXT,
        environment {json_type} DEFAULT '{{}}',
        industry {json_type} DEFAULT '[]',
        technique TEXT,
        conditions {json_type} DEFAULT '{{}}',
        source_article TEXT,
        source_type TEXT DEFAULT 'article',
        source_highlight_id TEXT,
        merged_from {json_type} DEFAULT '[]',
        usage_count INTEGER DEFAULT 0,
        last_used_at {timestamp_type},
        is_active INTEGER DEFAULT 1,
        version INTEGER DEFAULT 1,
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 15. Skill Learning Config table (Dynamic Merge Threshold)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS skill_learning_config (
        user_id {fk_type} PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        merge_threshold {numeric_type} DEFAULT 0.70,
        max_token_budget INTEGER DEFAULT 2000,
        last_token_usage INTEGER DEFAULT 0,
        total_skills_count INTEGER DEFAULT 0,
        updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 16. LLM Usage Logs table (Rule #8: Cognitive Memory Tiering)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS llm_usage_logs (
        id {pk_type},
        timestamp {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        user_id {fk_type} NOT NULL,
        agent_name TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        tier TEXT NOT NULL,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_cost_usd {numeric_type} DEFAULT 0,
        metadata {json_type} DEFAULT '{{}}'
    );
    """)

    # 17. Cognitive Memories table (Rule #8: Medium-Term Structured Storage)
    schema_commands.append(f"""
    CREATE TABLE IF NOT EXISTS cognitive_memories (
        id {pk_type},
        user_id {fk_type} NOT NULL {"REFERENCES users(id) ON DELETE CASCADE" if not is_sqlite else ""},
        agent_name TEXT NOT NULL,
        memory_type TEXT NOT NULL, -- 'insight', 'conviction', 'lesson', 'summary'
        content {json_type} NOT NULL,
        importance {numeric_type} DEFAULT 0.5,
        source_id TEXT, -- Original event_id or signal_id
        created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
        updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
    );
    """)

    if not is_sqlite:
        schema_commands.append("CREATE INDEX IF NOT EXISTS idx_llm_usage_user_ts ON llm_usage_logs(user_id, timestamp DESC);")
        schema_commands.append("CREATE INDEX IF NOT EXISTS idx_cog_mem_user_type ON cognitive_memories(user_id, memory_type);")

    with engine.connect() as conn:
        for cmd in schema_commands:
            try:
                conn.execute(text(cmd))
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Error executing schema command: {e}")
        
        # v4.1.7: Post-deployment strict migrations (UUID focus)
        # Add Unique Index for UPSERT on daily_snapshots if missing
        if not is_sqlite:
            try:
                # 1. Ensure Columns Exist
                cols_res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'daily_snapshots'")).fetchall()
                existing_cols = [c[0].lower() for c in cols_res]
                
                if 'account_id' not in existing_cols:
                    logger.info("Migrating: Adding account_id to daily_snapshots")
                    conn.execute(text("ALTER TABLE daily_snapshots ADD COLUMN account_id TEXT"))
                if 'conviction_level' not in existing_cols:
                    conn.execute(text(f"ALTER TABLE daily_snapshots ADD COLUMN conviction_level {numeric_type} DEFAULT 0"))
                if 'time_horizon' not in existing_cols:
                    conn.execute(text("ALTER TABLE daily_snapshots ADD COLUMN time_horizon TEXT"))
                
                # 2. Update Primary Key/Unique Index for Multi-Account support
                # First, ensure we don't have NULL account_ids before making it part of an index/PK
                conn.execute(text("UPDATE daily_snapshots SET account_id = '' WHERE account_id IS NULL"))
                
                # Update PK if necessary (Postgres specific)
                pk_check = conn.execute(text("""
                    SELECT count(*) FROM information_schema.key_column_usage 
                    WHERE table_name = 'daily_snapshots' AND constraint_name LIKE '%pkey%' 
                    AND column_name = 'account_id'
                """)).scalar()
                
                if pk_check == 0:
                    logger.info("Migrating: Updating daily_snapshots primary key to include account_id")
                    conn.execute(text("ALTER TABLE daily_snapshots DROP CONSTRAINT IF EXISTS daily_snapshots_pkey"))
                    conn.execute(text("ALTER TABLE daily_snapshots ADD PRIMARY KEY (date, user_id, account_id)"))

                # Update the UPSERT index
                logger.info("Updating daily_snapshots_upsert index to include account_id")
                conn.execute(text("DROP INDEX IF EXISTS idx_daily_snapshots_upsert"))
                conn.execute(text("CREATE UNIQUE INDEX idx_daily_snapshots_upsert ON daily_snapshots(date, user_id, account_id)"))

                # Ensure llm_usage_logs.id has a DEFAULT (migration for existing deployments)
                if not is_sqlite:
                    try:
                        conn.execute(text(
                            "ALTER TABLE llm_usage_logs ALTER COLUMN id SET DEFAULT gen_random_uuid()::text"
                        ))
                        logger.info("Migration: Added DEFAULT gen_random_uuid() to llm_usage_logs.id")
                    except Exception:
                        pass  # Already has a DEFAULT — ignore
                
            except Exception as e:
                logger.error(f"Failed to migrate daily_snapshots: {e}")
                # Don't raise here to allow boot, but log as error

        conn.commit()
    
    _db_initialized.add(db_url)
    logger.info(f"Database initialized with v4.1.7 optimized Postgres schema.")

if __name__ == "__main__":
    init_db()
