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
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._client: Optional[Any] = None  # lazy init

    def _key(self, user_id: str) -> str:
        return _REDIS_KEY_TEMPLATE.format(user_id=user_id)

    async def _get_client(self):
        """Lazy-initialize async Redis client."""
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                await self._client.ping()
                logger.info(f"RedisSentinelBuffer: Connected to {self._redis_url}")
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
                except Exception:
                    pass
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
                    except Exception:
                        pass
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
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"RedisSentinelBuffer.remove failed: {e}")
        return False

    async def size(self, user_id: str) -> int:
        """Return the number of pending triggers in the buffer."""
        try:
            r = await self._get_client()
            return await r.zcard(self._key(user_id))
        except Exception:
            return 0

    async def all_pending(self, user_id: str) -> List[Dict[str, Any]]:
        """List all pending triggers (for debugging)."""
        try:
            r = await self._get_client()
            members = await r.zrange(self._key(user_id), 0, -1)
            return [json.loads(m) for m in members]
        except Exception:
            return []
