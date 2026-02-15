"""
Extended tests for Sentinel Repository - CRUD & Query Operations.
測試 Sentinel 儲存庫的 CRUD 與查詢操作。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.data.sentinel_repository import SentinelRepository


class TestSentinelRepositoryExtended:
    """Extended tests for Sentinel Repository missing coverage."""
    
    @pytest.fixture
    def sentinel_repo(self):
        """Create sentinel repository with in-memory database."""
        repo = SentinelRepository(db_path=":memory:")
        return repo
    
    def test_create_sentinel_event(self, sentinel_repo):
        """Test creating a new sentinel event."""
        event_id = sentinel_repo.create_event(
            ticker="AAPL",
            event_type="earnings",
            severity=0.8,
            keywords=["beat", "earnings"],
            source="news"
        )
        
        assert event_id is not None
        assert isinstance(event_id, (int, str))
    
    def test_get_event_by_id(self, sentinel_repo):
        """Test retrieving event by ID."""
        # Create event first
        event_id = sentinel_repo.create_event(
            ticker="TSLA",
            event_type="legal",
            severity=0.9,
            keywords=["lawsuit"],
            source="news"
        )
        
        # Retrieve it
        event = sentinel_repo.get_by_id(event_id)
        
        assert event is not None
        assert event['ticker'] == "TSLA"
        assert event['event_type'] == "legal"
    
    def test_get_events_by_ticker(self, sentinel_repo):
        """Test querying events by ticker."""
        # Create multiple events
        sentinel_repo.create_event("AAPL", "earnings", 0.7, ["good"], "news")
        sentinel_repo.create_event("AAPL", "legal", 0.8, ["lawsuit"], "news")
        sentinel_repo.create_event("GOOGL", "earnings", 0.6, ["beat"], "news")
        
        # Query AAPL events
        events = sentinel_repo.get_by_ticker("AAPL")
        
        assert len(events) >= 2
        assert all(e['ticker'] == "AAPL" for e in events)
    
    def test_get_events_by_severity_threshold(self, sentinel_repo):
        """Test querying events above severity threshold."""
        # Create events with different severities
        sentinel_repo.create_event("AAPL", "legal", 0.9, ["critical"], "news")
        sentinel_repo.create_event("TSLA", "market", 0.5, ["minor"], "news")
        
        # Query high severity events
        events = sentinel_repo.get_by_severity(min_severity=0.8)
        
        assert len(events) >= 1
        assert all(e['severity'] >= 0.8 for e in events)
    
    def test_update_event_status(self, sentinel_repo):
        """Test updating event status."""
        event_id = sentinel_repo.create_event("AAPL", "earnings", 0.7, ["beat"], "news")
        
        # Update status
        sentinel_repo.update_status(event_id, "processed")
        
        event = sentinel_repo.get_by_id(event_id)
        assert event['status'] == "processed"
    
    def test_delete_event(self, sentinel_repo):
        """Test deleting an event."""
        event_id = sentinel_repo.create_event("AAPL", "test", 0.5, ["test"], "test")
        
        # Delete it
        sentinel_repo.delete(event_id)
        
        # Verify it's gone
        event = sentinel_repo.get_by_id(event_id)
        assert event is None
    
    def test_get_recent_events(self, sentinel_repo):
        """Test getting recent events with limit."""
        # Create multiple events
        for i in range(5):
            sentinel_repo.create_event(f"TICK{i}", "market", 0.6, ["test"], "news")
        
        # Get top 3 recent
        recent = sentinel_repo.get_recent(limit=3)
        
        assert len(recent) <= 3
    
    def test_query_events_by_date_range(self, sentinel_repo):
        """Test querying events within date range."""
        sentinel_repo.create_event("AAPL", "earnings", 0.7, ["test"], "news")
        
        events = sentinel_repo.get_by_date_range("2024-01-01", "2024-12-31")
        
        assert isinstance(events, list)
    
    def test_get_events_by_type(self, sentinel_repo):
        """Test filtering events by type."""
        sentinel_repo.create_event("AAPL", "earnings", 0.7, ["beat"], "news")
        sentinel_repo.create_event("TSLA", "legal", 0.8, ["lawsuit"], "news")
        sentinel_repo.create_event("GOOGL", "earnings", 0.6, ["miss"], "news")
        
        earnings_events = sentinel_repo.get_by_type("earnings")
        
        assert len(earnings_events) >= 2
        assert all(e['event_type'] == "earnings" for e in earnings_events)
