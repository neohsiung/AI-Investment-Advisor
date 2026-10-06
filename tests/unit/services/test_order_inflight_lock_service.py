import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.services.order_inflight_lock_service import OrderInflightLockService, _LOCAL_LOCKS


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_local_locks():
    _LOCAL_LOCKS.clear()
    yield
    _LOCAL_LOCKS.clear()


@pytest.mark.anyio
async def test_acquire_and_release_local_fallback():
    """Test lock acquire and release using local memory fallback when Redis is absent."""
    with patch("src.infrastructure.cache.redis_client.get_redis", side_effect=Exception("Redis down")):
        svc = OrderInflightLockService(user_id="user_123")
        
        # Initial state: unlocked
        assert not await svc.is_locked("TSM")
        
        # Acquire lock
        acq = await svc.acquire_lock("TSM", order_id="ord_1", action="BUY", ttl_seconds=60)
        assert acq is True
        assert await svc.is_locked("TSM")
        
        # Contention: same ticker cannot be acquired again
        acq2 = await svc.acquire_lock("TSM", order_id="ord_2", action="BUY")
        assert acq2 is False
        
        # Info retrieval
        info = await svc.get_lock_info("TSM")
        assert info is not None
        assert info["order_id"] == "ord_1"
        assert info["action"] == "BUY"
        
        # Release lock
        rel = await svc.release_lock("TSM")
        assert rel is True
        assert not await svc.is_locked("TSM")
        
        # Acquire again after release
        acq3 = await svc.acquire_lock("TSM", order_id="ord_3", action="SELL")
        assert acq3 is True


@pytest.mark.anyio
async def test_redis_lock_acquire_and_release():
    """Test lock acquire and release with mocked Redis."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = '{"order_id": "ord_99", "action": "BUY"}'
    mock_redis.exists.return_value = True
    mock_redis.delete.return_value = 1

    with patch("src.infrastructure.cache.redis_client.get_redis", return_value=mock_redis):
        svc = OrderInflightLockService(user_id="user_123")
        
        acq = await svc.acquire_lock("AAPL", order_id="ord_99", action="BUY", ttl_seconds=300)
        assert acq is True
        mock_redis.set.assert_called_once()
        
        locked = await svc.is_locked("AAPL")
        assert locked is True
        
        info = await svc.get_lock_info("AAPL")
        assert info["order_id"] == "ord_99"
        
        rel = await svc.release_lock("AAPL")
        assert rel is True
        mock_redis.delete.assert_called_once()
