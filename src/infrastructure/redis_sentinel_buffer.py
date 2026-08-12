"""
Redis-backed Sentinel Buffer
替換 in-memory dict，使容器重啟後的 trigger 不遺失。

Architecture:
  Redis Sorted Set per user:
    Key:    sentinel:buffer:{user_id}
    Member: JSON-encoded trigger dict
    Score:  UNIX timestamp of the deadline (when it should be flushed)

Operations:
  add()         → ZADD (score = now + deadline_minutes * 60)
  flush_due()   → ZRANGEBYSCORE 0..now → ZREMRANGEBYSCORE → return triggers
  remove()      → scan & ZREM by trigger id
  size()        → ZCARD
"""
import json
import time
import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("RedisSentinelBuffer")

_REDIS_KEY_TEMPLATE = "sentinel:buffer:{user_id}"


class RedisSentinelBuffer:
    """
    Persistent Sentinel trigger buffer backed by Redis Sorted Set.
    Redis Sorted Set 為底層的持久化 Sentinel 觸發緩衝區。
    """

    def __init__(self, redis_url: str = None):
        # `redis_url` is retained for API compatibility but is no longer used:
        # the client now comes from the process-wide pool, which resolves
        # REDIS_URL itself. No caller has ever passed an override.
        # redis_url 保留僅為相容；客戶端改由行程共用連線池提供，其自行解析
        # REDIS_URL。目前沒有任何呼叫端傳入覆寫值。
        self._redis_url = redis_url
        self._client: Optional[Any] = None  # lazy init

    def _key(self, user_id: str) -> str:
        return _REDIS_KEY_TEMPLATE.format(user_id=user_id)

    async def _get_client(self):
        """
        Return the process-wide async Redis client.
        取得行程共用的 async Redis 客戶端。

        2026-08-10: this used to cache a client per *instance*, which only
        helps when the owner is itself a singleton. SentinelService is
        constructed fresh per Celery task (tasks.py) and per webhook request
        (webhook_service.py), so each one minted and abandoned another pool.
        The shared accessor makes the caching process-wide instead.
        2026-08-10：原本以 instance 為單位快取，但 SentinelService 每個 Celery
        task 與每次 webhook 請求都重建，等於每次都新建並遺棄一個連線池。
        """
        if self._client is None:
            try:
                from src.infrastructure.cache.redis_client import get_redis

                self._client = await get_redis(decode_responses=True)
                await self._client.ping()
            except Exception as e:
                logger.error(f"RedisSentinelBuffer: Failed to connect to Redis: {e}")
                self._client = None
                raise
        return self._client

    async def add(self, user_id: str, trigger: Dict[str, Any], deadline_minutes: int) -> bool:
        """
        Add a trigger to the buffer.
        觸發器加入 buffer，deadline_minutes 後自動到期化。
        """
        try:
            r = await self._get_client()
            score = time.time() + deadline_minutes * 60
            member = json.dumps(trigger, ensure_ascii=False, default=str)
            key = self._key(user_id)
            # NX: only add if trigger_id not already present (dedup by id field)
            existing = await r.zrange(key, 0, -1)
            for m in existing:
                try:
                    t = json.loads(m)
                    if t.get("id") == trigger.get("id"):
                        logger.debug(f"RedisSentinelBuffer: Trigger {trigger.get('id')} already buffered, skipping.")
                        return False
                except Exception as e:
                    logger.warning(f'Exception in redis_sentinel_buffer.py: {e}', exc_info=True)
            await r.zadd(key, {member: score})
            logger.info(f"RedisSentinelBuffer: Buffered trigger {trigger.get('id')} for user {user_id[:8]}... deadline={deadline_minutes}m")
            return True
        except Exception as e:
            logger.error(f"RedisSentinelBuffer.add failed: {e}")
            return False

    async def flush_due(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Return all triggers whose deadlines have passed and remove them.
        取出所有已到期的觸發器並從 Redis 中刪除。
        """
        try:
            r = await self._get_client()
            key = self._key(user_id)
            now = time.time()
            members = await r.zrangebyscore(key, 0, now)
            if members:
                await r.zremrangebyscore(key, 0, now)
                triggers = []
                for m in members:
                    try:
                        triggers.append(json.loads(m))
                    except Exception as e:
                        logger.warning(f'Exception in redis_sentinel_buffer.py: {e}', exc_info=True)
                logger.info(f"RedisSentinelBuffer: Flushed {len(triggers)} due trigger(s) for user {user_id[:8]}...")
                return triggers
        except Exception as e:
            logger.error(f"RedisSentinelBuffer.flush_due failed: {e}")
        return []

    async def remove(self, user_id: str, trigger_id: str) -> bool:
        """
        Remove a specific trigger by its id field.
        根據 id 字段從 buffer 中刪除指定觸發器。
        """
        try:
            r = await self._get_client()
            key = self._key(user_id)
            members = await r.zrange(key, 0, -1)
            for m in members:
                try:
                    t = json.loads(m)
                    if t.get("id") == trigger_id:
                        await r.zrem(key, m)
                        logger.info(f"RedisSentinelBuffer: Removed trigger {trigger_id} for {user_id[:8]}...")
                        return True
                except Exception as e:
                    logger.warning(f'Exception in redis_sentinel_buffer.py: {e}', exc_info=True)
        except Exception as e:
            logger.error(f"RedisSentinelBuffer.remove failed: {e}")
        return False

    async def size(self, user_id: str) -> int:
        """Return the number of pending triggers in the buffer."""
        try:
            r = await self._get_client()
            return await r.zcard(self._key(user_id))
        except Exception as e:
            logger.warning(f'Exception in redis_sentinel_buffer.py: {e}', exc_info=True)
            return 0

    async def all_pending(self, user_id: str) -> List[Dict[str, Any]]:
        """List all pending triggers (for debugging)."""
        try:
            r = await self._get_client()
            members = await r.zrange(self._key(user_id), 0, -1)
            return [json.loads(m) for m in members]
        except Exception as e:
            logger.warning(f'Exception in redis_sentinel_buffer.py: {e}', exc_info=True)
            return []

    async def try_acquire(self, key: str, ttl_seconds: int) -> bool:
        """
        Best-effort distributed lock via SETNX+EX. Returns True if this caller
        won the key, False if someone already holds it.

        Deliberately FAILS OPEN: if Redis is unreachable the caller proceeds.
        The Sentinel is the system's safety monitor — skipping ticks is worse
        than an occasional duplicate — so a Redis outage must not silence it.
        Mirrors the fallback in WebhookService._acquire_concurrency_lock.

        There is no release method on purpose: the lock is released by TTL
        expiry only. Releasing on completion would re-open the very window the
        lock exists to close.
        以 SETNX+EX 實作的盡力鎖；Redis 失效時 fail-open 照跑（哨兵漏跑比重複更糟）。
        刻意不提供釋放方法 —— 提早釋放等於重開重複窗口，只靠 TTL 到期。
        """
        try:
            r = await self._get_client()
            acquired = await r.set(key, "1", nx=True, ex=ttl_seconds)
            return bool(acquired)
        except Exception as e:
            logger.warning(f"RedisSentinelBuffer.try_acquire failed for {key}, failing open: {e}")
            return True
