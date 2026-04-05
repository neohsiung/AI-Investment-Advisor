import asyncio
import logging
import sys
import os
import time
from sqlalchemy import text

# Ensure the project root is in sys.path
sys.path.append(os.getcwd())

from src.data.database import get_db_engine, get_async_db_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verify_Concurrency")

async def run_async_query(engine, task_id):
    """Runs a simple async query to verify connection handling."""
    start = time.time()
    try:
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with async_session() as session:
            # Simulate a small DB load
            result = await session.execute(text("SELECT 1"))
            await asyncio.sleep(0.1) # Simulate some processing delay
            val = result.scalar()
            # logger.debug(f"Task {task_id}: Success")
            return True
    except Exception as e:
        logger.error(f"Task {task_id} FAILED: {e}")
        return False

async def test_high_concurrency(concurrent_tasks=50):
    logger.info(f"--- 🔥 Testing Phase 19: High Concurrency ({concurrent_tasks} tasks) ---")
    engine = get_async_db_engine()
    
    start_time = time.time()
    tasks = [run_async_query(engine, i) for i in range(concurrent_tasks)]
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    success_count = sum(1 for r in results if r)
    
    logger.info(f"Completed {concurrent_tasks} tasks in {end_time - start_time:.2f}s")
    logger.info(f"Success Rate: {success_count}/{concurrent_tasks}")
    
    if success_count == concurrent_tasks:
        logger.info("✅ Connection Pool (size=20, overflow=50) handled the load perfectly.")
    else:
        logger.error("❌ Some tasks failed. Check pool settings.")

if __name__ == "__main__":
    asyncio.run(test_high_concurrency(50))
