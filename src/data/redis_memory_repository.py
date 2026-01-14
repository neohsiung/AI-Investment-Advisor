import redis
import json
import logging
import os
from typing import List
from datetime import datetime
from src.services.memory_service import IMemoryRepository, ReportMemoryItem

logger = logging.getLogger(__name__)

class RedisMemoryRepository(IMemoryRepository):
    """
    Redis implementation for Shared Agent Memory.
    Suitable for K8s microservices environment.
    """
    def __init__(self, redis_url: str = None):
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.r = redis.from_url(url, decode_responses=True)
        # Verify connection
        try:
            self.r.ping()
            logger.info(f"Connected to Redis at {url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")

    def _get_key_prefix(self, user_id: str, report_type: str) -> str:
        return f"memory:report:{user_id}:{report_type}"

    def save_report(self, item: ReportMemoryItem) -> None:
        """
        Save report content to a Hash and index it in a Sorted Set (ZSET).
        """
        # 1. Key for the specific report content
        # Format: memory:report:{uid}:{type}:content:{date}
        content_key = f"{self._get_key_prefix(item.user_id, item.report_type)}:content:{item.report_date}"
        
        # 2. Key for the index (time-series)
        # Format: memory:report:{uid}:{type}:index
        index_key = f"{self._get_key_prefix(item.user_id, item.report_type)}:index"
        
        # Data payload
        data = {
            "user_id": item.user_id,
            "report_type": item.report_type,
            "report_date": item.report_date,
            "full_content": item.full_content,
            "compressed_summary": item.compressed_summary or "",
            "key_findings": json.dumps(item.key_findings) if item.key_findings else ""
        }
        
        pipe = self.r.pipeline()
        
        # Save Content (Hash)
        pipe.hset(content_key, mapping=data)
        # Set expiry? Maybe keep for a long time. Let's say 90 days.
        pipe.expire(content_key, 60*60*24*90) 
        
        # Add to Index (Sorted Set), score check be timestamp
        try:
            dt = datetime.strptime(item.report_date, "%Y-%m-%d")
            score = dt.timestamp()
        except ValueError:
            score = 0
            
        # Value in ZSET is the content_key reference
        pipe.zadd(index_key, {content_key: score})
        
        pipe.execute()
        logger.info(f"Saved report to Redis: {content_key}")

    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        """
        Retrieve N most recent reports using ZREVRANGE.
        """
        index_key = f"{self._get_key_prefix(user_id, report_type)}:index"
        
        # Get last N keys (Reverse order -> newest first)
        content_keys = self.r.zrevrange(index_key, 0, limit - 1)
        
        if not content_keys:
            return []
            
        items = []
        for key in content_keys:
            data = self.r.hgetall(key)
            if data:
                items.append(ReportMemoryItem(
                    user_id=data.get("user_id"),
                    report_type=data.get("report_type"),
                    report_date=data.get("report_date"),
                    full_content=data.get("full_content"),
                    compressed_summary=data.get("compressed_summary") or None,
                    key_findings=json.loads(data.get("key_findings")) if data.get("key_findings") else None
                ))
        
        return items
