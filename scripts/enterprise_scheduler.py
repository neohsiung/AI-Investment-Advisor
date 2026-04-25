#!/usr/bin/env python3
"""
Enterprise Queue Integration Script
Enqueue daily/weekly reports to Redis queue for async processing
"""

import asyncio
import redis
import uuid
import sys
import os
import json
from datetime import datetime
from typing import Optional

# Redis configuration
REDIS_URL = os.getenv("QUEUE_REDIS_URL", "redis://advisor_prod_cache:6379")
REDIS_HOST = "advisor_prod_cache"
REDIS_PORT = 6379

class EnterpriseScheduler:
    """Simple synchronous queue manager for scheduling reports"""
    
    def __init__(self):
        self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    
    def enqueue_report(self, 
                      user_id: str,
                      report_type: str = "daily",
                      scheduled_date: Optional[str] = None,
                      priority: int = 50) -> str:
        """
        Enqueue a report generation job
        
        Args:
            user_id: User identifier
            report_type: 'daily', 'weekly', or 'monthly'
            scheduled_date: Target date (YYYY-MM-DD) or None for today
            priority: Priority level (0-100, 50=normal)
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        scheduled_date = scheduled_date or datetime.now().strftime("%Y-%m-%d")
        
        # Create job metadata
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "report_type": report_type,
            "scheduled_date": scheduled_date,
            "status": "queued",
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "current_stage": 1
        }
        
        queue_key = f"report:{report_type}:queue"
        
        # Store job metadata
        self.r.set(f"job:{job_id}:metadata", json.dumps(job_data), ex=86400)
        
        # Add to priority queue (score = priority, member = job_id)
        self.r.zadd(queue_key, {job_id: 100 - priority})  # Lower priority = higher score
        
        return job_id
    
    def get_queue_status(self, report_type: str = "daily") -> dict:
        """Get queue status"""
        queue_key = f"report:{report_type}:queue"
        depth = self.r.zcard(queue_key)
        
        # Get DLQ status
        dlq_key = "report:dlq:failed"
        dlq_depth = self.r.llen(dlq_key)
        
        return {
            "queue": queue_key,
            "depth": depth,
            "dlq_depth": dlq_depth,
            "timestamp": datetime.now().isoformat()
        }

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Enterprise Report Queue Manager")
    parser.add_argument("--enqueue", action="store_true", help="Enqueue a report")
    parser.add_argument("--user-id", required=False, 
                       default="90693c07-6177-42df-97d9-915f3ce7c573",
                       help="User ID")
    parser.add_argument("--report-type", default="daily", 
                       choices=["daily", "weekly", "monthly"],
                       help="Report type")
    parser.add_argument("--priority", type=int, default=50,
                       help="Priority (0-100, 50=normal)")
    parser.add_argument("--status", action="store_true", help="Check queue status")
    
    args = parser.parse_args()
    
    scheduler = EnterpriseScheduler()
    
    try:
        # Check Redis connection
        scheduler.r.ping()
        print("✅ Redis connected")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        sys.exit(1)
    
    if args.enqueue:
        job_id = scheduler.enqueue_report(
            user_id=args.user_id,
            report_type=args.report_type,
            priority=args.priority
        )
        print(f"✅ Report enqueued")
        print(f"   Job ID: {job_id}")
        print(f"   User: {args.user_id}")
        print(f"   Type: {args.report_type}")
        print(f"   Priority: {args.priority}")
    
    if args.status:
        status = scheduler.get_queue_status(args.report_type)
        print(f"✅ Queue status:")
        for k, v in status.items():
            print(f"   {k}: {v}")

if __name__ == "__main__":
    main()
