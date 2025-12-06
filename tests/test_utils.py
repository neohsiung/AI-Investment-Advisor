import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz
import os
from src.utils.time_utils import get_timezone, get_current_time, format_time, get_current_date_str
from src.utils.cache import ResponseCache

# --- Time Utils Tests ---
def test_get_timezone():
    # Test default
    if "TIMEZONE" in os.environ:
        del os.environ["TIMEZONE"]
    tz = get_timezone()
    assert str(tz) == "Asia/Taipei"
    
    # Test valid env var
    os.environ["TIMEZONE"] = "UTC"
    tz = get_timezone()
    assert str(tz) == "UTC"
    
    # Test invalid env var (fallback)
    os.environ["TIMEZONE"] = "Invalid/Timezone"
    tz = get_timezone()
    assert str(tz) == "Asia/Taipei"

def test_format_time():
    dt = datetime(2023, 1, 1, 12, 0, 0)
    assert format_time(dt) == "2023-01-01 12:00:00"
    
    # Test custom format
    assert format_time(dt, fmt="Year: %Y") == "Year: 2023"

# --- Cache Tests ---
@pytest.fixture
def test_cache_db(tmp_path):
    return str(tmp_path / "test_cache.db")

def test_cache_operations(test_cache_db):
    cache = ResponseCache(db_path=test_cache_db, ttl_hours=1)
    
    # Test Set
    cache.set("TestAgent", "Hello", "Response 1")
    
    # Test Get (Hit)
    resp = cache.get("TestAgent", "Hello")
    assert resp == "Response 1"
    
    # Test Get (Miss - Different Prompt)
    resp = cache.get("TestAgent", "Hi")
    assert resp is None
    
    # Test Get (Miss - Different Agent)
    resp = cache.get("OtherAgent", "Hello")
    assert resp is None

def test_cache_expiration(test_cache_db):
    cache = ResponseCache(db_path=test_cache_db, ttl_hours=-1) # Expire immediately
    cache.set("TestAgent", "Hello", "Response 1")
    
    resp = cache.get("TestAgent", "Hello")
    assert resp is None

def test_cache_clear(test_cache_db):
    cache = ResponseCache(db_path=test_cache_db)
    cache.set("TestAgent", "Hello", "Response 1")
    cache.clear()
    
    resp = cache.get("TestAgent", "Hello")
    assert resp is None
