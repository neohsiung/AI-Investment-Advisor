import redis
import hashlib
import json
import os
import logging
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import timedelta, datetime
from src.utils.logger import setup_logger
from src.utils.time_utils import get_current_time

class ResponseCache:
    """
    Redis-based cache for agent responses.
    使用 Redis 的 Agent 回應快取層。
    """
    def __init__(self, redis_url: str = None, ttl_hours: int = 24):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.ttl_seconds = ttl_hours * 3600
        self.logger = setup_logger("ResponseCache")
        self.client = redis.from_url(self.redis_url, decode_responses=True)
        
        # Verify connection
        try:
            self.client.ping()
            self.logger.info(f"Connected to Redis cache at {self.redis_url}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis cache: {e}")

    def _generate_key(self, agent_name: str, prompt: str) -> str:
        """Generate a unique Redis key based on agent name and prompt content."""
        content = f"{agent_name}:{prompt}"
        hashed = hashlib.sha256(content.encode('utf-8')).hexdigest()
        return f"cache:response:{agent_name}:{hashed}"

    def get(self, agent_name: str, prompt: str) -> Optional[str]:
        """Retrieve a cached response if valid."""
        key = self._generate_key(agent_name, prompt)
        try:
            val = self.client.get(key)
            if val:
                self.logger.info(f"Cache HIT for {agent_name}")
                return val
            return None
        except Exception as e:
            self.logger.error(f"Cache GET error: {e}")
            return None

    def set(self, agent_name: str, prompt: str, response: str):
        """Save a response to the cache with TTL."""
        key = self._generate_key(agent_name, prompt)
        try:
            # Atomic set with expiration
            self.client.setex(key, self.ttl_seconds, response)
            self.logger.info(f"Cache SET for {agent_name} (TTL: {self.ttl_seconds}s)")
        except Exception as e:
            self.logger.error(f"Cache SET error: {e}")

    def clear(self):
        """Clear all cache entries matching the prefix."""
        try:
            keys = self.client.keys("cache:response:*")
            if keys:
                self.client.delete(*keys)
                self.logger.info(f"Cleared {len(keys)} cache entries.")
        except Exception as e:
            self.logger.error(f"Cache CLEAR error: {e}")

    def get_value(self, key: str) -> Optional[str]:
        """Retrieve generic value from cache."""
        try:
            return self.client.get(key)
        except Exception as e:
            self.logger.error(f"Cache get_value error for key {key}: {e}")
            return None

    def set_value(self, key: str, value: str, ttl_seconds: int = None):
        """Store generic value in cache with optional TTL."""
        try:
            ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
            self.client.setex(key, ttl, value)
        except Exception as e:
            self.logger.error(f"Cache set_value error for key {key}: {e}")

    def delete_value(self, key: str):
        """Remove value from cache."""
        try:
            self.client.delete(key)
        except Exception as e:
            self.logger.error(f"Cache delete_value error for key {key}: {e}")
