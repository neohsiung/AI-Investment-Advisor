import pytest
import time
import asyncio
from unittest.mock import patch
from src.utils.rate_limiter import TokenBucketLimiter, rate_limit, RateLimitExceeded, _user_limiters

@pytest.fixture(autouse=True)
def reset_limiters():
    """Reset the global _user_limiters dict before each test."""
    _user_limiters.clear()
    yield
    _user_limiters.clear()

@pytest.mark.asyncio
async def test_token_bucket_consume():
    limiter = TokenBucketLimiter(requests_per_minute=60)
    assert limiter.capacity == 60
    assert limiter.tokens == 60.0
    
    # Consume 1 token
    allowed = await limiter.consume()
    assert allowed is True
    assert limiter.tokens < 60.0
    
    # Consume remaining tokens
    for _ in range(59):
        assert await limiter.consume() is True
        
    # Should be empty now
    allowed = await limiter.consume()
    assert allowed is False
    
    # Wait for 1 second (1 token = 1 req/sec)
    with patch("time.time", return_value=time.time() + 1.1):
        allowed = await limiter.consume()
        assert allowed is True

@pytest.mark.asyncio
async def test_rate_limit_decorator_kwargs():
    @rate_limit(requests_per_minute=2)
    async def sample_func(user_id: str):
        return "success"
        
    res = await sample_func(user_id="test_user_1")
    assert res == "success"
    
    res = await sample_func(user_id="test_user_1")
    assert res == "success"
    
    with pytest.raises(RateLimitExceeded, match="Too many requests"):
        await sample_func(user_id="test_user_1")

@pytest.mark.asyncio
async def test_rate_limit_decorator_args():
    class DummyAgent:
        def __init__(self, uid):
            self._user_id = uid
            
    @rate_limit(requests_per_minute=1)
    async def sample_func(agent, data):
        return "success"
        
    agent = DummyAgent("test_user_2")
    res = await sample_func(agent, {})
    assert res == "success"
    
    with pytest.raises(RateLimitExceeded):
        await sample_func(agent, {})

@pytest.mark.asyncio
async def test_rate_limit_decorator_anonymous():
    @rate_limit(requests_per_minute=1)
    async def sample_func():
        return "success"
        
    res = await sample_func()
    assert res == "success"
    
    with pytest.raises(RateLimitExceeded):
        await sample_func()
