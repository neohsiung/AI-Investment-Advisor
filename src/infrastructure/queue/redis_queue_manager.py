"""
Redis Queue Manager for Report Job Distribution

This module handles:
- Job enqueueing with priority support
- Queue state management
- Lock mechanisms for preventing duplicate processing
- Dead Letter Queue (DLQ) for failed jobs

Usage:
    manager = RedisQueueManager()
    job_id = await manager.enqueue_job(user_id, 'daily', '2026-04-23')
    job = await manager.dequeue_job()
    await manager.mark_job_complete(job_id)
"""

import redis.asyncio as redis
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job lifecycle statuses."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DLQ = "dlq"  # Dead Letter Queue


@dataclass
class QueueJob:
    """Schema for jobs stored in Redis queue."""
    job_id: str
    user_id: str
    report_type: str  # 'daily', 'weekly'
    scheduled_date: str  # YYYY-MM-DD
    priority: int  # 0-100 (higher = more urgent)
    created_at: str
    retry_count: int = 0
    source: str = "scheduler"  # or "manual"
    metadata: Dict[str, Any] = None
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        data['metadata'] = self.metadata or {}
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'QueueJob':
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


class RedisQueueManager:
    """
    Manages Redis-backed job queues with priority support.
    
    Queue Structure:
    - report:daily:queue        # Daily reports (sorted by priority + created_at)
    - report:weekly:queue       # Weekly reports
    - report:priority:queue     # Manual/priority jobs
    - report:dlq:failed         # Failed jobs (after 3 retries)
    - job:${job_id}:lock        # Distributed lock
    - job:${job_id}:state       # Current job state (HSET)
    """
    
    def __init__(self, redis_url: str = None):
        """
        Initialize the queue manager.
        
        Args:
            redis_url: Redis connection URL. Defaults to env QUEUE_REDIS_URL or redis://localhost:6379
        """
        self.redis_url = redis_url or os.getenv('QUEUE_REDIS_URL', 'redis://localhost:6379')
        self.redis: Optional[redis.Redis] = None
        
        # Queue names
        self.DAILY_QUEUE = 'report:daily:queue'
        self.WEEKLY_QUEUE = 'report:weekly:queue'
        self.PRIORITY_QUEUE = 'report:priority:queue'
        self.DLQ_QUEUE = 'report:dlq:failed'
        
        # Configuration
        self.MAX_RETRIES = 3
        self.LOCK_TIMEOUT = 300  # 5 minutes
        self.JOB_TIMEOUT = 3600  # 1 hour
    
    async def connect(self):
        """Establish Redis connection."""
        self.redis = await redis.from_url(self.redis_url)
        logger.info(f"Connected to Redis: {self.redis_url}")
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
    
    async def enqueue_job(self, 
                         user_id: str, 
                         report_type: str,
                         scheduled_date: str,
                         priority: int = 50,
                         source: str = "scheduler") -> str:
        """
        Enqueue a new report generation job.
        
        Args:
            user_id: User identifier
            report_type: 'daily' or 'weekly'
            scheduled_date: YYYY-MM-DD format
            priority: 0-100 (50 = normal)
            source: 'scheduler' or 'manual'
            
        Returns:
            job_id (UUID)
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        job = QueueJob(
            job_id=job_id,
            user_id=user_id,
            report_type=report_type,
            scheduled_date=scheduled_date,
            priority=priority,
            created_at=now,
            source=source
        )
        
        # Choose queue based on priority and type
        if priority > 75:
            queue_name = self.PRIORITY_QUEUE
        elif report_type == 'daily':
            queue_name = self.DAILY_QUEUE
        else:
            queue_name = self.WEEKLY_QUEUE
        
        # Score = (-priority, created_at) for sorting
        # Higher priority gets processed first (negative for reverse sort)
        score = -priority * 1000000 + int(datetime.fromisoformat(now).timestamp())
        
        # Add to queue (sorted set for priority)
        await self.redis.zadd(queue_name, {job.to_json(): score})
        
        # Store job metadata in Redis
        await self.redis.hset(
            f'job:{job_id}:state',
            mapping={
                'status': JobStatus.QUEUED.value,
                'user_id': user_id,
                'report_type': report_type,
                'created_at': now,
                'current_stage': '0'
            }
        )
        
        # Set expiry for job state (1 day)
        await self.redis.expire(f'job:{job_id}:state', 86400)
        
        logger.info(f"Enqueued job {job_id} for user {user_id} (type={report_type}, priority={priority})")
        return job_id
    
    async def dequeue_job(self, worker_id: str) -> Optional[QueueJob]:
        """
        Dequeue the next job from all queues (priority-aware).
        Automatically acquires lock to prevent duplicate processing.
        
        Args:
            worker_id: Identifier for this worker (for lock ownership)
            
        Returns:
            QueueJob if available, None if all queues empty
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        # Try queues in order: priority > daily > weekly
        for queue_name in [self.PRIORITY_QUEUE, self.DAILY_QUEUE, self.WEEKLY_QUEUE]:
            # Pop from front (lowest score = highest priority)
            result = await self.redis.bzpopmin(queue_name, timeout=1)
            if result:
                queue, job_json, score = result
                job = QueueJob.from_json(job_json)
                
                # Try to acquire lock
                lock_key = f'job:{job.job_id}:lock'
                lock_acquired = await self.redis.set(
                    lock_key,
                    worker_id,
                    ex=self.LOCK_TIMEOUT,
                    nx=True  # Only set if not exists
                )
                
                if lock_acquired:
                    # Update job state to running
                    await self.redis.hset(
                        f'job:{job.job_id}:state',
                        'status',
                        JobStatus.RUNNING.value
                    )
                    await self.redis.hset(
                        f'job:{job.job_id}:state',
                        'started_at',
                        datetime.utcnow().isoformat()
                    )
                    
                    logger.info(f"Worker {worker_id} dequeued job {job.job_id}")
                    return job
                else:
                    # Lock already held, re-enqueue with slightly lower priority
                    # to prevent starvation
                    job.retry_count += 1
                    score_penalty = -10000 * job.retry_count
                    await self.redis.zadd(queue_name, {job.to_json(): score + score_penalty})
                    logger.warning(f"Job {job.job_id} lock held by another worker, re-queued")
                    continue
        
        return None
    
    async def mark_job_complete(self, job_id: str, report_id: str = None):
        """
        Mark job as successfully completed.
        
        Args:
            job_id: Job identifier
            report_id: Generated report ID (optional, for reference)
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        lock_key = f'job:{job_id}:lock'
        state_key = f'job:{job_id}:state'
        
        await self.redis.delete(lock_key)  # Release lock
        
        await self.redis.hset(state_key, mapping={
            'status': JobStatus.COMPLETED.value,
            'completed_at': datetime.utcnow().isoformat(),
            'report_id': report_id or ''
        })
        
        logger.info(f"Job {job_id} marked as completed (report_id={report_id})")
    
    async def mark_job_failed(self, job_id: str, error_message: str = None):
        """
        Mark job as failed. After MAX_RETRIES, move to DLQ.
        
        Args:
            job_id: Job identifier
            error_message: Description of failure
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        lock_key = f'job:{job_id}:lock'
        state_key = f'job:{job_id}:state'
        
        await self.redis.delete(lock_key)  # Release lock
        
        # Get current retry count
        retry_count = int(await self.redis.hget(state_key, 'retry_count') or 0)
        retry_count += 1
        
        if retry_count >= self.MAX_RETRIES:
            # Move to DLQ
            job_data = await self.redis.hgetall(state_key)
            await self.redis.hset(
                f'job:{job_id}:dlq',
                mapping={
                    **job_data,
                    'status': JobStatus.DLQ.value,
                    'failed_at': datetime.utcnow().isoformat(),
                    'error_message': error_message or 'Unknown error',
                    'final_retry_count': retry_count
                }
            )
            await self.redis.lpush(self.DLQ_QUEUE, job_id)
            logger.error(f"Job {job_id} moved to DLQ after {retry_count} retries")
        else:
            # Retry
            await self.redis.hset(state_key, mapping={
                'status': JobStatus.QUEUED.value,
                'retry_count': retry_count,
                'last_error': error_message or 'Unknown error'
            })
            logger.warning(f"Job {job_id} marked for retry ({retry_count}/{self.MAX_RETRIES})")
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get current status of a job.
        
        Returns:
            Dict with status, stage, timestamps, etc.
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        state = await self.redis.hgetall(f'job:{job_id}:state')
        if not state:
            return {'error': f'Job {job_id} not found'}
        
        return {
            'job_id': job_id,
            'status': state.get(b'status', b'').decode(),
            'user_id': state.get(b'user_id', b'').decode(),
            'report_type': state.get(b'report_type', b'').decode(),
            'current_stage': int(state.get(b'current_stage', b'0')),
            'created_at': state.get(b'created_at', b'').decode(),
            'started_at': state.get(b'started_at', b'').decode(),
            'completed_at': state.get(b'completed_at', b'').decode(),
            'retry_count': int(state.get(b'retry_count', b'0')),
            'report_id': state.get(b'report_id', b'').decode()
        }
    
    async def get_queue_depth(self) -> Dict[str, int]:
        """Get current depth of all queues."""
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        return {
            'daily': await self.redis.zcard(self.DAILY_QUEUE),
            'weekly': await self.redis.zcard(self.WEEKLY_QUEUE),
            'priority': await self.redis.zcard(self.PRIORITY_QUEUE),
            'dlq': await self.redis.llen(self.DLQ_QUEUE)
        }
    
    async def list_dlq_jobs(self, limit: int = 10) -> List[str]:
        """List job IDs in Dead Letter Queue."""
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        return await self.redis.lrange(self.DLQ_QUEUE, 0, limit - 1)
    
    async def resume_from_checkpoint(self, job_id: str, from_stage: int = 0) -> bool:
        """
        Resume a failed job from a specific stage checkpoint.
        
        Args:
            job_id: Job to resume
            from_stage: Stage to resume from (0-5)
            
        Returns:
            True if successfully queued, False otherwise
        """
        if not self.redis:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        
        state = await self.redis.hgetall(f'job:{job_id}:state')
        if not state:
            logger.error(f"Cannot resume: job {job_id} not found")
            return False
        
        # Re-queue the job
        user_id = state[b'user_id'].decode()
        report_type = state[b'report_type'].decode()
        
        # Update state
        await self.redis.hset(f'job:{job_id}:state', mapping={
            'status': JobStatus.QUEUED.value,
            'current_stage': str(from_stage),
            'resumed_at': datetime.utcnow().isoformat()
        })
        
        logger.info(f"Job {job_id} resumed from stage {from_stage}")
        return True
    
    async def health_check(self) -> bool:
        """Check Redis connection health."""
        if not self.redis:
            return False
        
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


# Export for use
__all__ = ['RedisQueueManager', 'QueueJob', 'JobStatus']
