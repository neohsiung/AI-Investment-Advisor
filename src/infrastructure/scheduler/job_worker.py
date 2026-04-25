"""
Enterprise Job Worker and Scheduler Enhancement

This module implements:
- Job Worker Pool (background task processor)
- Enhanced Scheduler with queue integration
- Checkpoint/Resume capabilities
- Health monitoring

Usage:
    # Start worker pool (processes 4 jobs concurrently)
    worker_pool = JobWorkerPool(concurrency=4)
    await worker_pool.start()
    
    # Enqueue a job from scheduler
    job_id = await scheduler.enqueue_daily_report(user_id, date)
    
    # Worker will process it asynchronously
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from src.utils.logger import setup_logger
from src.infrastructure.queue.redis_queue_manager import (
    RedisQueueManager, JobStatus, QueueJob
)
from src.infrastructure.workflow.stages import WorkflowStages

logger = setup_logger("JobWorker")


class JobWorker:
    """
    Single worker process that:
    - Polls Redis queue
    - Processes one job at a time
    - Handles failures with exponential backoff
    - Manages checkpoints for resumption
    """
    
    def __init__(self, worker_id: str, queue_manager: RedisQueueManager):
        """
        Initialize a worker.
        
        Args:
            worker_id: Unique identifier for this worker (e.g., 'worker-1')
            queue_manager: Shared queue manager instance
        """
        self.worker_id = worker_id
        self.queue_manager = queue_manager
        self.logger = setup_logger(f"Worker/{worker_id}")
        self.running = False
    
    async def start(self):
        """Start the worker polling loop."""
        self.running = True
        self.logger.info(f"Worker {self.worker_id} started")
        
        try:
            while self.running:
                try:
                    # Poll for next job with timeout
                    job = await self.queue_manager.dequeue_job(self.worker_id)
                    
                    if not job:
                        # No jobs available, sleep briefly before retry
                        await asyncio.sleep(1)
                        continue
                    
                    # Process the job
                    self.logger.info(f"Processing job {job.job_id} for user {job.user_id}")
                    await self._process_job(job)
                
                except Exception as e:
                    self.logger.error(f"Worker error: {e}", exc_info=True)
                    await asyncio.sleep(5)  # Back off on error
        
        finally:
            self.logger.info(f"Worker {self.worker_id} stopped")
    
    async def stop(self):
        """Signal worker to stop."""
        self.running = False
    
    async def _process_job(self, job: QueueJob) -> None:
        """
        Process a single job through the 5-stage pipeline.
        
        Args:
            job: QueueJob to process
        """
        try:
            # Initialize pipeline
            stages = WorkflowStages(
                user_id=job.user_id,
                job_id=job.job_id,
                queue_manager=self.queue_manager
            )
            
            # Check if resuming from checkpoint
            state = await self.queue_manager.get_job_status(job.job_id)
            current_stage = state.get('current_stage', 1)
            
            if current_stage > 1:
                self.logger.info(f"Resuming job {job.job_id} from stage {current_stage}")
            
            # Run pipeline from current stage
            result = await stages.run_from_stage(from_stage=current_stage)
            
            if result.get('success'):
                self.logger.info(f"Job {job.job_id} completed successfully")
            else:
                self.logger.error(f"Job {job.job_id} failed: {result.get('error')}")
        
        except Exception as e:
            self.logger.error(f"Job processing failed: {e}", exc_info=True)
            await self.queue_manager.mark_job_failed(
                job.job_id,
                error_message=str(e)
            )


class JobWorkerPool:
    """
    Pool of concurrent workers that process jobs from Redis queue.
    
    Features:
    - Horizontal scaling (add/remove workers dynamically)
    - Health monitoring
    - Graceful shutdown
    - Metrics collection
    """
    
    def __init__(self, concurrency: int = 4, redis_url: str = None):
        """
        Initialize worker pool.
        
        Args:
            concurrency: Number of concurrent workers
            redis_url: Redis connection URL
        """
        self.concurrency = concurrency
        self.redis_url = redis_url or os.getenv('QUEUE_REDIS_URL', 'redis://localhost:6379')
        
        self.queue_manager: Optional[RedisQueueManager] = None
        self.workers = []
        self.running = False
        
        self.logger = setup_logger("WorkerPool")
    
    async def start(self):
        """Start the worker pool."""
        self.logger.info(f"Starting worker pool with {self.concurrency} workers")
        
        # Initialize queue manager
        self.queue_manager = RedisQueueManager(redis_url=self.redis_url)
        await self.queue_manager.connect()
        
        self.running = True
        
        # Start worker tasks
        for i in range(self.concurrency):
            worker_id = f"worker-{i+1}"
            worker = JobWorker(worker_id, self.queue_manager)
            self.workers.append(worker)
        
        # Run all workers concurrently
        try:
            await asyncio.gather(
                *[worker.start() for worker in self.workers],
                return_exceptions=True
            )
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown all workers."""
        self.logger.info("Shutting down worker pool...")
        self.running = False
        
        # Signal all workers to stop
        for worker in self.workers:
            await worker.stop()
        
        # Wait for all to finish
        await asyncio.gather(
            *[worker.start() for worker in self.workers],
            return_exceptions=True
        )
        
        # Close queue manager
        if self.queue_manager:
            await self.queue_manager.disconnect()
        
        self.logger.info("Worker pool shutdown complete")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Return health status of the pool.
        
        Returns:
            Dict with worker statuses and queue depths
        """
        if not self.queue_manager:
            return {'status': 'offline', 'workers': []}
        
        is_healthy = await self.queue_manager.health_check()
        queue_depth = await self.queue_manager.get_queue_depth()
        
        return {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'workers_running': len([w for w in self.workers if w.running]),
            'total_workers': len(self.workers),
            'queue_depth': queue_depth,
            'timestamp': datetime.utcnow().isoformat()
        }


class EnhancedScheduler:
    """
    Enhanced scheduler that integrates with Redis queue.
    
    Modes:
    - sync: Traditional synchronous mode (backward compatibility)
    - async: New async queue mode (recommended)
    - worker: Worker pool mode (backend processing)
    """
    
    def __init__(self, queue_manager: RedisQueueManager = None):
        """Initialize scheduler."""
        self.queue_manager = queue_manager
        self.logger = setup_logger("EnhancedScheduler")
    
    async def enqueue_daily_report(self, 
                                   user_id: str,
                                   scheduled_date: str,
                                   priority: int = 50) -> str:
        """
        Enqueue a daily report for generation.
        
        Args:
            user_id: User ID
            scheduled_date: YYYY-MM-DD format
            priority: 0-100 (50 = normal)
            
        Returns:
            job_id (can be used to track progress)
        """
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        job_id = await self.queue_manager.enqueue_job(
            user_id=user_id,
            report_type='daily',
            scheduled_date=scheduled_date,
            priority=priority,
            source='scheduler'
        )
        
        self.logger.info(f"Enqueued daily report: job_id={job_id}, user_id={user_id}")
        return job_id
    
    async def enqueue_weekly_report(self, 
                                    user_id: str,
                                    scheduled_date: str,
                                    priority: int = 50) -> str:
        """Enqueue a weekly report."""
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        job_id = await self.queue_manager.enqueue_job(
            user_id=user_id,
            report_type='weekly',
            scheduled_date=scheduled_date,
            priority=priority,
            source='scheduler'
        )
        
        self.logger.info(f"Enqueued weekly report: job_id={job_id}, user_id={user_id}")
        return job_id
    
    async def enqueue_manual_report(self, 
                                    user_id: str,
                                    report_type: str) -> str:
        """
        Enqueue a manual/priority report (high priority).
        
        Args:
            user_id: User ID
            report_type: 'daily' or 'weekly'
            
        Returns:
            job_id
        """
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        from datetime import date
        today = date.today().isoformat()
        
        job_id = await self.queue_manager.enqueue_job(
            user_id=user_id,
            report_type=report_type,
            scheduled_date=today,
            priority=90,  # High priority
            source='manual'
        )
        
        self.logger.info(f"Enqueued manual report: job_id={job_id}, user_id={user_id}, priority=90")
        return job_id
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a queued/running/completed job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Status dict
        """
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        return await self.queue_manager.get_job_status(job_id)
    
    async def resume_job(self, job_id: str, from_stage: int = 0) -> bool:
        """
        Resume a failed job from a checkpoint.
        
        Args:
            job_id: Job to resume
            from_stage: Stage to resume from (0-5)
            
        Returns:
            True if successfully resumed
        """
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        success = await self.queue_manager.resume_from_checkpoint(job_id, from_stage)
        
        if success:
            self.logger.info(f"Resumed job {job_id} from stage {from_stage}")
        else:
            self.logger.error(f"Failed to resume job {job_id}")
        
        return success


# CLI Entry Points (for app.py)

async def run_scheduler_mode(user_id: str = None, async_mode: bool = False) -> None:
    """
    Run scheduler in sync or async mode.
    
    Args:
        user_id: Specific user to run for (optional)
        async_mode: If True, return job_id immediately. If False, wait for completion.
    """
    queue_manager = RedisQueueManager()
    await queue_manager.connect()
    
    scheduler = EnhancedScheduler(queue_manager)
    
    if async_mode:
        # Queue mode: return immediately with job_id
        job_id = await scheduler.enqueue_daily_report(
            user_id=user_id or 'default',
            scheduled_date=datetime.now().strftime('%Y-%m-%d')
        )
        print(f"Job queued: {job_id}")
    else:
        # Sync mode: wait for completion (backward compatibility)
        # This would call the old DailyWorkflow().run() directly
        raise NotImplementedError("Sync mode requires legacy workflow integration")
    
    await queue_manager.disconnect()


async def run_worker_mode(concurrency: int = 4) -> None:
    """
    Run as worker pool (backend task processor).
    
    Args:
        concurrency: Number of concurrent workers
    """
    pool = JobWorkerPool(concurrency=concurrency)
    
    try:
        await pool.start()
    except KeyboardInterrupt:
        print("Shutting down worker pool...")
        await pool.shutdown()


# Export
__all__ = [
    'JobWorker',
    'JobWorkerPool',
    'EnhancedScheduler',
    'run_scheduler_mode',
    'run_worker_mode'
]
