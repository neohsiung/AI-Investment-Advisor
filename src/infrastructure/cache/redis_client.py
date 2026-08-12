"""
Process-wide Redis clients backed by a single shared connection pool.
以單一共用連線池為底的行程級 Redis 客戶端。

Why this module exists / 為何需要此模組
──────────────────────────────────────
2026-08-10 outage: `advisor_prod_api` held 10,003 ESTABLISHED sockets to
Redis and exhausted the 10,000 `maxclients` ceiling, which starved every
Celery worker with `ConnectionError: max number of clients reached`. The
trading loop was down for three days.

Root cause was `redis==5.0.1`'s asyncio `Connection`, which — unlike its
sync counterpart — defines no `__del__`, so an un-`aclose()`d client leaks
its socket for the lifetime of the process. Garbage collection cannot
reclaim it. Fourteen call sites each built their own `from_url()` client
and only one ever closed it; the `/health` endpoint built a fresh async
client every 30 seconds on the Docker healthcheck.

The fix is structural rather than per-site: one pool per process, bounded
by `max_connections`, so a missing `close()` can no longer grow the
socket count without limit. Prefer these accessors over `from_url()`.

2026-08-10 故障：async client 未關閉導致 socket 洩漏、打滿 maxclients，
交易迴圈停擺三天。改為單一有界連線池，讓漏關 close() 不再能無限增長。

Usage / 用法
────────────
    from src.infrastructure.cache.redis_client import get_redis, get_redis_sync

    r = await get_redis()          # async — do NOT close; the pool is shared
    await r.ping()

    r = get_redis_sync()           # sync — likewise, do NOT close

Only `aclose_redis()` / `close_redis_sync()` tear the pools down, and only
at process shutdown (e.g. FastAPI lifespan teardown).
"""
import os
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("RedisClient")

# Bounded so a leaked reference can never exhaust the server's maxclients.
# The whole API process shares these, so the ceiling is per-container.
# 設上限：即使有洩漏的參考也不可能耗盡伺服器的 maxclients。
_DEFAULT_MAX_CONNECTIONS = 20

_async_client: Optional[Any] = None
_sync_client: Optional[Any] = None

# Guards lazy init. Async callers are single-threaded per event loop, but
# the sync accessor is reachable from Celery's prefork workers and from
# FastAPI's threadpool, so both share one lock for simplicity.
# 保護延遲初始化；sync 版會被 Celery prefork 與 FastAPI threadpool 呼叫。
_lock = threading.Lock()


def _redis_url() -> str:
    """
    Resolve the Redis URL.

    `REDIS_URL` is the only variable docker-compose.prod.yml actually sets.
    `CELERY_BROKER_URL` was referenced by some call sites but has never been
    defined in prod, so those silently fell back to a password-less URL and
    failed AUTH against a `--requirepass` server. Read only `REDIS_URL`.
    僅讀 REDIS_URL；CELERY_BROKER_URL 在 prod 從未設定，會退化成無密碼連線。
    """
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


def _max_connections() -> int:
    raw = os.getenv("REDIS_MAX_CONNECTIONS", "").strip()
    if not raw:
        return _DEFAULT_MAX_CONNECTIONS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            f"Invalid REDIS_MAX_CONNECTIONS={raw!r}, falling back to {_DEFAULT_MAX_CONNECTIONS}"
        )
        return _DEFAULT_MAX_CONNECTIONS
    if value < 1:
        logger.warning(
            f"REDIS_MAX_CONNECTIONS={value} is below 1, falling back to {_DEFAULT_MAX_CONNECTIONS}"
        )
        return _DEFAULT_MAX_CONNECTIONS
    return value


async def get_redis(decode_responses: bool = True) -> Any:
    """
    Return the process-wide async Redis client. Never close the result.
    取得行程共用的 async Redis 客戶端；呼叫端不得關閉。

    The client is created on first use and reused thereafter. `from_url`
    builds its own pool internally, which is exactly what we want to share.
    """
    global _async_client
    if _async_client is None:
        with _lock:
            if _async_client is None:
                import redis.asyncio as aioredis

                _async_client = aioredis.from_url(
                    _redis_url(),
                    decode_responses=decode_responses,
                    max_connections=_max_connections(),
                    socket_connect_timeout=2,
                    # Recycles sockets the server has dropped, instead of
                    # surfacing a stale-connection error to the caller.
                    # 回收伺服器端已斷開的 socket，避免把陳舊連線錯誤丟給呼叫端。
                    health_check_interval=30,
                )
                logger.info(
                    f"Shared async Redis pool created (max_connections={_max_connections()})"
                )
    return _async_client


def get_redis_sync(decode_responses: bool = True) -> Any:
    """
    Return the process-wide sync Redis client. Never close the result.
    取得行程共用的 sync Redis 客戶端；呼叫端不得關閉。
    """
    global _sync_client
    if _sync_client is None:
        with _lock:
            if _sync_client is None:
                import redis

                _sync_client = redis.from_url(
                    _redis_url(),
                    decode_responses=decode_responses,
                    max_connections=_max_connections(),
                    socket_connect_timeout=2,
                    health_check_interval=30,
                )
                logger.info(
                    f"Shared sync Redis pool created (max_connections={_max_connections()})"
                )
    return _sync_client


async def aclose_redis() -> None:
    """
    Tear down the async pool. Call once at process shutdown only.
    關閉 async 連線池；僅在行程結束時呼叫一次。
    """
    global _async_client
    client = _async_client
    _async_client = None
    if client is None:
        return
    try:
        # `aclose()` is the 5.x name; `close()` is the deprecated alias.
        await client.aclose()
    except AttributeError:
        await client.close()
    except Exception as e:
        logger.warning(f"Error closing async Redis pool: {e}")


def close_redis_sync() -> None:
    """
    Tear down the sync pool. Call once at process shutdown only.
    關閉 sync 連線池；僅在行程結束時呼叫一次。
    """
    global _sync_client
    client = _sync_client
    _sync_client = None
    if client is None:
        return
    try:
        client.close()
    except Exception as e:
        logger.warning(f"Error closing sync Redis pool: {e}")
