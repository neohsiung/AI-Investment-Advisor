import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import os
from src.utils.time_utils import get_timezone, format_time
from src.utils.cache import ResponseCache

# --- Time Utils Tests ---
def test_get_timezone():
    # Test default
    if "TIMEZONE" in os.environ:
        del os.environ["TIMEZONE"]
    tz = get_timezone()
    # default in time_utils seems to be Asia/Taipei
    assert str(tz) == "Asia/Taipei"

    # Test valid env var
    with patch('src.utils.time_utils.get_db_timezone', return_value=None):
        os.environ["TIMEZONE"] = "UTC"
        tz = get_timezone()
        assert str(tz) == "UTC"

    # Test invalid env var (fallback)
    os.environ["TIMEZONE"] = "Invalid/Timezone"
    tz = get_timezone()
    # It might fallback to system or default
    assert str(tz) == "Asia/Taipei"

def test_format_time():
    dt = datetime(2023, 1, 1, 12, 0, 0)
    assert format_time(dt) == "2023-01-01 12:00:00"

    # Test custom format
    assert format_time(dt, fmt="Year: %Y") == "Year: 2023"

# --- Cache Tests (Redis Mocked) ---
@pytest.fixture
def mock_redis():
    with patch('redis.from_url') as mock_from_url:
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client
        yield mock_client

def test_cache_operations(mock_redis):
    cache = ResponseCache(ttl_hours=1)
    
    # Test Set
    cache.set("TestAgent", "Hello", "Response 1")
    assert mock_redis.setex.called
    
    # Test Get (Hit)
    mock_redis.get.return_value = "Response 1"
    resp = cache.get("TestAgent", "Hello")
    assert resp == "Response 1"
    
    # Test Get (Miss)
    mock_redis.get.return_value = None
    resp = cache.get("TestAgent", "Hi")
    assert resp is None

def test_cache_clear(mock_redis):
    cache = ResponseCache()
    mock_redis.keys.return_value = ["key1", "key2"]
    
    cache.clear()
    
    mock_redis.keys.assert_called_with("cache:response:*")
    mock_redis.delete.assert_called()
