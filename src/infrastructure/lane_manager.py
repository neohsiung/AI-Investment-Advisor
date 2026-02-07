import asyncio
import logging
import time
from typing import Dict, Any, Callable, Awaitable, List

logger = logging.getLogger(__name__)

class LaneManager:
    """
    OpenClaw Layer 2: Control Plane (Lane Queue).
    Manages concurrency by enforcing sequential execution per session_id (Lane).
    Supports 'run_batch' for parallel execution within a locked session context.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LaneManager, cls).__new__(cls)
            cls._instance.lanes: Dict[str, asyncio.Queue] = {}
            cls._instance.workers: Dict[str, asyncio.Task] = {}
        return cls._instance

    def get_lane(self, session_id: str) -> asyncio.Queue:
        """
        Retrieves or creates the Queue for a specific session.
        """
        if session_id not in self.lanes:
            # Create an unbounded queue for the session
            self.lanes[session_id] = asyncio.Queue()
            # Start the worker for this lane
            self.workers[session_id] = asyncio.create_task(self._process_lane(session_id))
            logger.info(f"LaneManager: Created new lane for session {session_id}")
        return self.lanes[session_id]

    async def enqueue(self, session_id: str, task_func: Callable[[], Awaitable[Any]]) -> asyncio.Future:
        """
        Enqueues a task to be executed sequentially in the session's lane.
        Returns a Future that will hold the result of the task.
        """
        lane = self.get_lane(session_id)
        
        # Create a future to return the result to the caller
        result_future = asyncio.get_running_loop().create_future()
        
        # Push the (task_func, result_future) tuple to the queue
        await lane.put((task_func, result_future))
        logger.debug(f"LaneManager: Enqueued task for session {session_id}")
        
        return result_future

    async def _process_lane(self, session_id: str):
        """
        The background worker that processes tasks from the lane strictly sequentially (FIFO).
        """
        lane = self.lanes[session_id]
        
        while True:
            # Wait for next task
            task_func, result_future = await lane.get()
            
            try:
                # Execute valid task
                if task_func:
                    start_time = time.time()
                    # Await the coroutine function
                    result = await task_func()
                    
                    # Set result
                    if not result_future.done():
                        result_future.set_result(result)
                    
                    duration = time.time() - start_time
                    logger.debug(f"LaneManager: Task completed for {session_id} in {duration:.4f}s")
                    
            except Exception as e:
                logger.error(f"LaneManager: Task failed for {session_id}: {e}")
                if not result_future.done():
                    result_future.set_exception(e)
            finally:
                lane.task_done()

    async def run_batch(self, tasks: List[Callable[[], Awaitable[Any]]], batch_size: int = 5) -> List[Any]:
        """
        Executes a list of async tasks in parallel batches.
        Useful for Map-Reduce operations (e.g., scanning 20 tickers).
        
        This helper calls asyncio.gather in chunks. It is NOT strictly serialized 
        by the session lane itself (the caller should wrap this whole batch op 
        in a single lane task if they want to lock the session during the batch).
        """
        logger.info(f"LaneManager: Starting batch of {len(tasks)} tasks (Batch Size: {batch_size})")
        results = []
        
        for i in range(0, len(tasks), batch_size):
            chunk = tasks[i : i + batch_size]
            # Execute chunk in parallel
            chunk_results = await asyncio.gather(*[t() for t in chunk], return_exceptions=True)
            results.extend(chunk_results)
            
        return results

    async def shutdown(self):
        """
        Cancel all workers.
        """
        for sid, task in self.workers.items():
            task.cancel()
        # Optionally wait for tasks
