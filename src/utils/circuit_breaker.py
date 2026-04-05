"""
Circuit Breaker Utility — Infrastructure Layer [Phase 15].
熔斷器工具 — 用於防止外部相依服務故障導致的連線雪崩。
"""

import time
import logging
import asyncio
import functools
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreakerOpenError(Exception):
    """Exception raised when a request is blocked by an open circuit."""
    pass

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        expected_exceptions: tuple = (Exception,)
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None

    def __call__(self, func: Callable):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self._async_call(func, *args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self._sync_call(func, *args, **kwargs)
            return sync_wrapper

    def _sync_call(self, func, *args, **kwargs):
        self._before_call()
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as e:
            self._on_failure(e)
            raise e

    async def _async_call(self, func, *args, **kwargs):
        self._before_call()
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as e:
            self._on_failure(e)
            raise e

    def _before_call(self):
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - (self.last_failure_time or 0)
            if elapsed > self.recovery_timeout:
                logger.info(f"⚡ CircuitBreaker '{self.name}': Transitioning OPEN -> HALF-OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN. Cooling down...")

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"✅ CircuitBreaker '{self.name}': Transitioning HALF-OPEN -> CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self, exception: Exception):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"❌ CircuitBreaker '{self.name}': Failure count {self.failure_count}/{self.failure_threshold}. Error: {exception}")
        
        if self.failure_count >= self.failure_threshold:
            logger.error(f"⚠️ CircuitBreaker '{self.name}': Transitioning to OPEN state for {self.recovery_timeout}s")
            self.state = CircuitState.OPEN

def circuit_breaker(name: str, failure_threshold: int = 3, recovery_timeout: int = 60):
    """Decorator factory for easier application."""
    cb = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return cb
