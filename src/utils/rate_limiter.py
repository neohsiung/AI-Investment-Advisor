"""
Rate Limiter Utility — SaaS Layer [Phase 16].
速率限制工具 — 採用 Token Bucket 演算法，防止 API 過度調用。
"""

import time
import asyncio
import logging
import functools
from typing import Dict, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    """Exception raised when a user exceeds the allowed request rate."""
    pass

class TokenBucketLimiter:
    """
    In-memory Token Bucket Rate Limiter.
    For production with multiple instances, this should be refactored to use Redis.
    """
    def __init__(self, requests_per_minute: int = 10):
        self.capacity = requests_per_minute
        self.tokens = float(requests_per_minute)
        self.last_refill = time.time()
        self.refill_rate = requests_per_minute / 60.0 # tokens per second
        self._lock = asyncio.Lock()

    async def consume(self):
        async with self._lock:
            now = time.time()
            # Refill tokens since last call
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
            self.last_refill = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

# Global registry for user-based limiters
_user_limiters: Dict[str, TokenBucketLimiter] = {}

def rate_limit(requests_per_minute: int = 10):
    """
    User-based rate limiting decorator.
    Expects 'user_id' to be present in the decorated function's context or arguments.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Attempt to extract user_id from various common locations
            user_id = kwargs.get("user_id")
            if not user_id and args and hasattr(args[0], "_user_id"):
                user_id = args[0]._user_id
            if not user_id:
                user_id = "anonymous"
            
            if user_id not in _user_limiters:
                _user_limiters[user_id] = TokenBucketLimiter(requests_per_minute)
            
            limiter = _user_limiters[user_id]
            if await limiter.consume():
                return await func(*args, **kwargs)
            else:
                logger.warning(f"Rate limit exceeded for user {user_id}: {requests_per_minute} req/min")
                raise RateLimitExceeded(f"Too many requests. Rate limit is {requests_per_minute} per minute.")
        
        return wrapper
    return decorator
