import pytest
from unittest.mock import MagicMock, patch
import os
import json
from src.repositories.redis_memory_repository import RedisMemoryRepository
from src.services.memory_factory import MemoryFactory
from src.services.memory_service import MemoryService, ReportMemoryItem

# --- Redis Repository Tests ---

class MockRedis:
    def __init__(self):
        self.data = {}
        self.pipeline_called = False
    
    def ping(self):
        return True
    
    def pipeline(self):
        self.pipeline_called = True
        return self
    
    def hset(self, key, mapping):
        self.data[key] = mapping
    
    def expire(self, key, time):
        pass
        
    def zadd(self, key, mapping):
        # simplified mock: mapping is {member: score}
        if key not in self.data: self.data[key] = {}
        self.data[key].update(mapping)
        
    def execute(self):
        pass
        
    def zrevrange(self, key, start, end):
        # Return keys stored in zadd
        if key in self.data:
            return list(self.data[key].keys())
        return []
        
    def hgetall(self, key):
        return self.data.get(key, {})

# 2026-08-10: patch target moved from `redis.from_url` to the shared pool
# accessor. RedisMemoryRepository no longer builds its own client — see
# src/infrastructure/cache/redis_client.py for why.
# 2026-08-10：patch 目標由 redis.from_url 改為共用連線池存取函式。
@patch('src.infrastructure.cache.redis_client.get_redis_sync')
def test_redis_repo_save_and_fetch(mock_get_redis):
    mock_r = MockRedis()
    mock_get_redis.return_value = mock_r

    repo = RedisMemoryRepository("redis://mock")
    
    item = ReportMemoryItem(
        user_id="u1",
        report_type="daily",
        report_date="2023-01-01",
        full_content="Content",
        compressed_summary="Sum",
        key_findings={"k":"v"}
    )
    
    # Test Save
    repo.save_report(item)
    assert "memory:report:u1:daily:content:2023-01-01" in mock_r.data
    
    # Test Fetch
    items = repo.get_recent_reports("u1", "daily", 5)
    assert len(items) == 1
    assert items[0].full_content == "Content"
    assert items[0].key_findings == {"k":"v"}

# --- Memory Factory Tests ---

@patch('src.services.memory_factory.RedisMemoryRepository')
@patch('src.services.memory_factory.AlchemyMemoryRepository')
def test_memory_factory_switching(mock_sqlite, mock_redis):
    # Case 1: Default (SQLite)
    if "MEMORY_BACKEND" in os.environ: del os.environ["MEMORY_BACKEND"]
    
    service = MemoryFactory.create_memory_service("u1")
    assert isinstance(service, MemoryService)
    mock_sqlite.assert_called()
    
    # Case 2: Redis
    os.environ["MEMORY_BACKEND"] = "redis"
    os.environ["REDIS_URL"] = "redis://host"
    
    service_r = MemoryFactory.create_memory_service("u1")
    mock_redis.assert_called()
