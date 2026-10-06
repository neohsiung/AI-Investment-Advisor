"""
Order In-Flight Lock Service.
標的交易在途鎖與訂單冪等性管理器。

Responsible for:
1. Preventing concurrent/duplicate order dispatch for the same ticker.
2. Holding locks across order placement and asynchronous reconciliation confirmation.
3. Automatically releasing locks on completion (filled, cancelled, rejected, expired, unresolved).
4. Providing dual-tier lock storage: distributed Redis with graceful in-process memory fallback.
"""

import json
import time
import asyncio
from typing import Optional, Dict, Any
from src.utils.logger import setup_logger
from src.config.owner import resolve_user_id

logger = setup_logger("OrderInflightLockService")

# Global in-memory fallback for process-local lock guarantees when Redis is unavailable
_LOCAL_LOCKS: Dict[str, Dict[str, Any]] = {}
_LOCAL_LOCK_MUTEX = asyncio.Lock()


class OrderInflightLockService:
    """
    Manages ticker-level in-flight execution locks.
    管理標的級別的在途交易鎖，杜絕併發重複送單。
    """

    _KEY_PREFIX = "order:inflight"
    DEFAULT_TTL_SECONDS = 1800  # 30 minutes default TTL

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)

    def _get_key(self, user_id: str, ticker: str) -> str:
        uid = resolve_user_id(user_id or self.user_id)
        sym = (ticker or "").strip().upper()
        return f"{self._KEY_PREFIX}:{uid}:{sym}"

    async def acquire_lock(
        self,
        ticker: str,
        user_id: Optional[str] = None,
        order_id: Optional[str] = None,
        action: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        strategy_name: Optional[str] = None,
    ) -> bool:
        """
        Attempt to acquire an in-flight lock for the given ticker.
        嘗試為指定標的獲取在途鎖。

        Returns:
            True if lock was acquired, False if already held.
        """
        uid = resolve_user_id(user_id or self.user_id)
        sym = (ticker or "").strip().upper()
        if not uid or not sym:
            logger.warning(f"acquire_lock rejected: invalid user_id={uid} or ticker={sym}")
            return False

        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        key = self._get_key(uid, sym)
        now_ts = time.time()
        payload = {
            "user_id": uid,
            "ticker": sym,
            "order_id": str(order_id or ""),
            "action": str(action or "").upper(),
            "strategy_name": strategy_name or "AutomatedTrading",
            "acquired_at": now_ts,
            "expires_at": now_ts + ttl,
        }
        val_str = json.dumps(payload)

        # 1. Try Redis
        try:
            from src.infrastructure.cache.redis_client import get_redis
            redis = await get_redis()
            # SET key val NX EX ttl
            acquired = await redis.set(key, val_str, nx=True, ex=ttl)
            if acquired:
                logger.info(f"🔒 [InflightLock] Acquired Redis lock for {uid}:{sym} (TTL={ttl}s, order_id={order_id})")
                return True
            else:
                existing_raw = await redis.get(key)
                existing_meta = json.loads(existing_raw) if existing_raw else {}
                logger.warning(
                    f"⛔ [InflightLock] Lock contention for {uid}:{sym}: already held by "
                    f"order={existing_meta.get('order_id')} action={existing_meta.get('action')}"
                )
                return False
        except Exception as redis_err:
            logger.warning(f"[InflightLock] Redis unavailable ({redis_err}); falling back to local lock")

        # 2. Local Fallback
        async with _LOCAL_LOCK_MUTEX:
            existing = _LOCAL_LOCKS.get(key)
            if existing and existing.get("expires_at", 0) > now_ts:
                logger.warning(
                    f"⛔ [InflightLock] Local lock contention for {uid}:{sym}: held by "
                    f"order={existing.get('order_id')} action={existing.get('action')}"
                )
                return False
            _LOCAL_LOCKS[key] = payload
            logger.info(f"🔒 [InflightLock] Acquired local memory lock for {uid}:{sym} (TTL={ttl}s)")
            return True

    async def release_lock(
        self,
        ticker: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Release the in-flight lock for the given ticker.
        釋放指定標的的在途鎖。
        """
        uid = resolve_user_id(user_id or self.user_id)
        sym = (ticker or "").strip().upper()
        if not uid or not sym:
            return False

        key = self._get_key(uid, sym)
        released = False

        # 1. Try Redis
        try:
            from src.infrastructure.cache.redis_client import get_redis
            redis = await get_redis()
            deleted = await redis.delete(key)
            if deleted:
                released = True
                logger.info(f"🔓 [InflightLock] Released Redis lock for {uid}:{sym}")
        except Exception as redis_err:
            logger.warning(f"[InflightLock] Redis delete error ({redis_err})")

        # 2. Clear local memory lock
        async with _LOCAL_LOCK_MUTEX:
            if key in _LOCAL_LOCKS:
                _LOCAL_LOCKS.pop(key, None)
                released = True
                logger.info(f"🔓 [InflightLock] Released local memory lock for {uid}:{sym}")

        return released

    async def is_locked(
        self,
        ticker: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Check if an in-flight lock is currently active for the given ticker.
        檢查指定標的是否正處於在途鎖定中。
        """
        uid = resolve_user_id(user_id or self.user_id)
        sym = (ticker or "").strip().upper()
        if not uid or not sym:
            return False

        key = self._get_key(uid, sym)
        now_ts = time.time()

        # 1. Check Redis
        try:
            from src.infrastructure.cache.redis_client import get_redis
            redis = await get_redis()
            exists = await redis.exists(key)
            if exists:
                return True
        except Exception as redis_err:
            logger.debug(f"[InflightLock] Redis check failed ({redis_err}); checking local")

        # 2. Check Local Fallback
        async with _LOCAL_LOCK_MUTEX:
            existing = _LOCAL_LOCKS.get(key)
            if existing:
                if existing.get("expires_at", 0) > now_ts:
                    return True
                else:
                    _LOCAL_LOCKS.pop(key, None)

        return False

    async def get_lock_info(
        self,
        ticker: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata of the active lock, or None if unlocked.
        獲取在途鎖的中繼資訊。
        """
        uid = resolve_user_id(user_id or self.user_id)
        sym = (ticker or "").strip().upper()
        if not uid or not sym:
            return None

        key = self._get_key(uid, sym)

        try:
            from src.infrastructure.cache.redis_client import get_redis
            redis = await get_redis()
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass

        async with _LOCAL_LOCK_MUTEX:
            existing = _LOCAL_LOCKS.get(key)
            if existing and existing.get("expires_at", 0) > time.time():
                return existing

        return None
