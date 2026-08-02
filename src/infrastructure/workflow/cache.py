import os
import json
import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class WorkflowCache:
    """
    Multi-level cache for workflow nodes.
    Tries Async Redis, falls back to SQLite, then to local memory dict.
    """
    def __init__(self, db_path: str = "workflow_cache.db", disable_cache: Optional[bool] = None):
        if disable_cache is None:
            self.disable_cache = os.getenv("DISABLE_WORKFLOW_CACHE", "false").lower() == "true"
        else:
            self.disable_cache = disable_cache
        self.db_path = db_path
        
        # Local in-memory dictionary backup
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # Redis client lazy setup
        self._redis_client = None
        self._redis_failed = False
        
        # Local SQLite setup
        self._sqlite_initialized = False
        if not self.disable_cache:
            self._init_sqlite()

    def _init_sqlite(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflow_cache (
                    cache_key TEXT PRIMARY KEY,
                    node_name TEXT,
                    inputs_json TEXT,
                    outputs_json TEXT,
                    expires_at TEXT,
                    created_at TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_wf_cache_expiry ON workflow_cache (expires_at);
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_telemetry (
                    metric_key TEXT PRIMARY KEY,
                    metric_val REAL DEFAULT 0.0
                );
            """)
            conn.commit()
            conn.close()
            self._sqlite_initialized = True
        except Exception as e:
            logger.warning(f"WorkflowCache: Failed to initialize SQLite cache: {e}")

    async def _get_redis(self):
        if self.disable_cache or self._redis_failed:
            return None
            
        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis
                url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                password = os.getenv("REDIS_PASSWORD")
                
                kwargs = {
                    "decode_responses": True,
                    "socket_connect_timeout": 2,
                }
                if password:
                    kwargs["password"] = password
                    
                self._redis_client = aioredis.from_url(url, **kwargs)
                await self._redis_client.ping()
                logger.info(f"WorkflowCache: Connected to Redis at {url}")
            except Exception as e:
                logger.warning(f"WorkflowCache: Redis unavailable ({e}). Falling back to SQLite/Memory.")
                self._redis_client = None
                self._redis_failed = True
                
        return self._redis_client

    def _make_key(self, node_name: str, inputs: Dict[str, Any]) -> str:
        # Standardize inputs to sorted JSON string to ensure key stability
        input_str = json.dumps(inputs, sort_keys=True, default=str)
        inputs_hash = hashlib.sha256(input_str.encode("utf-8")).hexdigest()
        return f"wf_cache:node:{node_name}:{inputs_hash}"

    async def get(self, node_name: str, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.disable_cache:
            return None

        cache_key = self._make_key(node_name, inputs)
        
        # 1. Try Redis
        try:
            r_client = await self._get_redis()
            if r_client:
                cached_val = await r_client.get(cache_key)
                if cached_val:
                    logger.debug(f"WorkflowCache [Redis Hit] Node '{node_name}'")
                    return json.loads(cached_val)
        except Exception as e:
            logger.warning(f"WorkflowCache: Redis get failed: {e}")
            self._redis_failed = True
            
        # 2. Try SQLite
        if self._sqlite_initialized:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT outputs_json, expires_at FROM workflow_cache WHERE cache_key = ?",
                    (cache_key,)
                )
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    outputs_json, expires_at_str = row
                    expires_at = datetime.fromisoformat(expires_at_str)
                    now = datetime.now(timezone.utc) if expires_at.tzinfo else datetime.now()
                    
                    if expires_at > now:
                        logger.debug(f"WorkflowCache [SQLite Hit] Node '{node_name}'")
                        return json.loads(outputs_json)
                    else:
                        # Clean up expired entry
                        await self._delete_sqlite_key(cache_key)
            except Exception as e:
                logger.warning(f"WorkflowCache: SQLite get failed: {e}")
                
        # 3. Try In-Memory dictionary
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            now = datetime.now(timezone.utc)
            if entry["expires_at"] > now:
                logger.debug(f"WorkflowCache [Memory Hit] Node '{node_name}'")
                return entry["outputs"]
            else:
                del self._memory_cache[cache_key]
                
        return None

    async def set(self, node_name: str, inputs: Dict[str, Any], outputs: Dict[str, Any], ttl_seconds: int):
        if self.disable_cache or ttl_seconds <= 0:
            return

        cache_key = self._make_key(node_name, inputs)
        outputs_str = json.dumps(outputs)
        
        # 1. Try Redis
        try:
            r_client = await self._get_redis()
            if r_client:
                await r_client.set(cache_key, outputs_str, ex=ttl_seconds)
                logger.debug(f"WorkflowCache [Redis Set] Node '{node_name}' TTL={ttl_seconds}s")
                return
        except Exception as e:
            logger.warning(f"WorkflowCache: Redis set failed: {e}")
            self._redis_failed = True

        # 2. Try SQLite
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        
        if self._sqlite_initialized:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO workflow_cache 
                    (cache_key, node_name, inputs_json, outputs_json, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cache_key,
                        node_name,
                        json.dumps(inputs, sort_keys=True, default=str),
                        outputs_str,
                        expires_at.isoformat(),
                        now.isoformat()
                    )
                )
                conn.commit()
                conn.close()
                logger.debug(f"WorkflowCache [SQLite Set] Node '{node_name}' TTL={ttl_seconds}s")
                return
            except Exception as e:
                logger.warning(f"WorkflowCache: SQLite set failed: {e}")

        # 3. Fallback to In-Memory dictionary
        self._memory_cache[cache_key] = {
            "outputs": outputs,
            "expires_at": expires_at
        }
        logger.debug(f"WorkflowCache [Memory Set] Node '{node_name}' TTL={ttl_seconds}s")

    async def _delete_sqlite_key(self, cache_key: str):
        if not self._sqlite_initialized:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workflow_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"WorkflowCache: SQLite delete failed for {cache_key}: {e}")

    async def clear_expired(self):
        """Clean up all expired SQLite and in-memory entries."""
        now = datetime.now(timezone.utc)
        
        # SQLite clean
        if self._sqlite_initialized:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM workflow_cache WHERE expires_at < ?", (now.isoformat(),))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"WorkflowCache: SQLite clear_expired failed: {e}")
                
        # In-memory clean
        expired_keys = [k for k, v in self._memory_cache.items() if v["expires_at"] < now]
        for k in expired_keys:
            del self._memory_cache[k]

    async def increment_metric(self, metric_key: str, amount: float = 1.0):
        if self.disable_cache:
            return
        if self._sqlite_initialized:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO cache_telemetry (metric_key, metric_val)
                    VALUES (?, ?)
                    ON CONFLICT(metric_key) DO UPDATE SET metric_val = metric_val + ?
                    """,
                    (metric_key, amount, amount)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"WorkflowCache: Failed to increment metric {metric_key}: {e}")

    async def get_all_telemetry(self) -> Dict[str, float]:
        telemetry = {
            "total_workflow_runs": 0.0,
            "cache_hits": 0.0,
            "cache_misses": 0.0,
            "saved_cost_usd": 0.0
        }
        if self._sqlite_initialized:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT metric_key, metric_val FROM cache_telemetry")
                rows = cursor.fetchall()
                conn.close()
                for key, val in rows:
                    if key in telemetry:
                        telemetry[key] = float(val)
            except Exception as e:
                logger.warning(f"WorkflowCache: Failed to fetch telemetry: {e}")
        return telemetry
