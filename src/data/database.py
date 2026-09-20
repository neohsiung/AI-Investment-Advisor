import os
import logging
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# v8.0 Global Async Engine Cache
_async_db_engines: Dict[str, AsyncEngine] = {}

# Global Engine Cache
_db_engines: Dict[str, Engine] = {}

# 2026-08-02: the global `_session_registries` (one shared scoped_session per
# Engine) is GONE. It was the root of a real concurrency defect: engines are
# cached by URL, so the whole process shared one registry, and scoped_session
# without a scopefunc scopes to threading.local() — but FastAPI runs every
# coroutine on ONE event-loop thread, so "thread-local" meant "shared by every
# concurrent request". One coroutine's `finally: close_session()` tore down a
# session another was mid-use of, and any `commit()` expired everyone's
# objects. Sessions are now per repository INSTANCE, with optional injection
# for a caller-owned unit of work.
# 2026-08-02：移除全域 scoped_session registry。FastAPI 所有 coroutine 同一執行緒，
# thread-local 等同「所有請求共用」，一個 close_session() 會拆掉別人正在用的 session。

# Global Initialization Registry to track which databases have been initialized
_db_initialized: set = set()

class BaseRepository:
    def __init__(self, engine: Engine, session: Any = None):
        """
        `session` lets a caller supply its own unit of work (e.g. a
        per-request session) so several repositories can share one
        transaction. When supplied, this repository never commits or closes
        it — lifecycle belongs to whoever created it.
        傳入 session 可讓多個 repository 共用一個交易；此時本物件不會 commit 或關閉它。
        """
        self.engine = engine
        self._external_session = session
        # expire_on_commit=False: repositories legitimately return ORM objects
        # that outlive their session (llm_tier_binding_repository does this on
        # the hot LLM path). Expiring on commit turns those into
        # DetachedInstanceError landmines.
        # 讓 commit 後仍可讀已載入屬性；否則跨 session 回傳的 ORM 物件會變地雷。
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._session = None

    @property
    def session(self):
        """
        The session for this repository instance.

        MEMOIZED on purpose. Several methods read `self.session` more than
        once in a single body — e.g. `usage_repository` does
        `self.session.add(...)` then `self.session.commit()`. Returning a new
        session per access would add to one and commit another, silently
        losing the write.
        必須 memoize：多處方法在同一 body 內兩次讀取，回傳新 session 會靜默丟失寫入。
        """
        if self._external_session is not None:
            return self._external_session
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def close_session(self):
        """Close this instance's session. Never touches an injected one."""
        if self._external_session is not None:
            return
        if self._session is not None:
            self._session.close()
            self._session = None

    @contextmanager
    def session_scope(self):
        """
        Preferred idiom: commit on clean exit, roll back on error, always close.
        An injected session is yielded as-is — the owner commits and closes it.
        建議用法；若為外部注入的 session 則原樣讓出，由擁有者負責 commit/close。
        """
        if self._external_session is not None:
            yield self._external_session
            return
        s = self._session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
    
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
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
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
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
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
    Returns a SQLAlchemy Session object.
    v19.1: Changed from Connection to Session to support ORM .query() in legacy repos.
    """
    engine = get_db_engine(db_path)
    factory = sessionmaker(bind=engine)
    return factory()

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
    
    # ── Schema creation ──────────────────────────────────────────────────
    #
    # This used to be ~430 lines of hand-written `CREATE TABLE IF NOT EXISTS`
    # covering 27 tables — a second, drifting copy of src/data/models.py. The
    # drift was not hypothetical: the ORM-only `decision_outcomes` model never
    # reached this path, so tests/conftest.py had to hand-create that table to
    # stop TradingProtectionsService (which fails CLOSED on a query error) from
    # blocking every BUY in tests.
    #
    # The ORM models are the single source of truth now, matching what the
    # deployment path (scripts/init_db.py) has always done. Adding a model makes
    # it appear here automatically.
    #
    # Production is unaffected: containers run `alembic upgrade head`, and
    # scripts/init_db.py create_all()s + stamps only when alembic_version is
    # absent (a genuinely fresh database).
    #
    # 原本是 ~430 行手寫 DDL，等於 models.py 的第二份會漂移的副本；
    # 改以 ORM 為單一真相，與部署路徑一致。新增 model 會自動生效。
    if not is_sqlite:
        with engine.connect() as conn:
            for ext in ('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
                        'CREATE EXTENSION IF NOT EXISTS "vector";'):
                try:
                    conn.execute(text(ext))
                except Exception as e:
                    logger.warning(f"Could not create extension: {e}")
            conn.commit()

    import src.data.models  # noqa: F401  — registers every model on Base.metadata
    from src.data.models import Base

    Base.metadata.create_all(engine, checkfirst=True)

    _db_initialized.add(db_url)
    logger.info("Database schema ensured from ORM models (src/data/models.py).")

if __name__ == "__main__":
    init_db()
