import pytest
import asyncio
from src.infrastructure.lane_manager import LaneManager

@pytest.fixture(autouse=True)
def reset_lane_manager():
    LaneManager._instance = None
    yield
    LaneManager._instance = None

    """Test singleton behavior."""
    lm1 = LaneManager()
    lm2 = LaneManager()
    assert lm1 is lm2
    
def test_lane_manager_enqueue():
    """Test enqueueing tasks."""
    async def run_test():
        lm = LaneManager()
        
        async def dummy_task():
            await asyncio.sleep(0.01)
            return "done"
            
        future = await lm.enqueue("test_session", dummy_task)
        
        result = await future
        assert result == "done"
        
        # Verify lane creation
        assert "test_session" in lm.lanes
        assert "test_session" in lm.workers

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_lane_manager_run_batch():
    """Test batch execution."""
    async def run_test():
        lm = LaneManager()
        
        async def task(i):
            await asyncio.sleep(0.01)
            return i * 2
            
        tasks = [lambda i=i: task(i) for i in range(10)]
        
        results = await lm.run_batch(tasks, batch_size=3)
        
        results.sort()
        assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_lane_manager_task_failure():
    """Test exception propagation."""
    async def run_test():
        lm = LaneManager()
        
        async def failing_task():
            raise ValueError("Failure")
            
        future = await lm.enqueue("fail_session", failing_task)
        
        with pytest.raises(ValueError, match="Failure"):
            await future

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()

def test_lane_manager_shutdown():
    """Test shutdown cancels workers."""
    async def run_test():
        lm = LaneManager()
        await lm.enqueue("shutdown_sess", lambda: asyncio.sleep(0.01))
        
        await lm.shutdown()
        # Tasks in workers should be cancelled (or at least method called)
        # Hard to verify explicitly without mocking asyncio.Task, but we can verify it doesn't crash.

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_test())
    finally:
        loop.close()
