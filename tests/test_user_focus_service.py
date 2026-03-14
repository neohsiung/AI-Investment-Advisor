
import pytest
from unittest.mock import MagicMock
from src.services.user_focus_service import UserFocusService

def test_get_user_focus_empty():
    """Verify empty result when no watchlists."""
    mock_etoro = MagicMock()
    mock_etoro.get_watchlists.return_value = []
    
    service = UserFocusService(user_id="test_user", etoro_service=mock_etoro)
    focus = service.get_user_focus()
    assert focus == {}

def test_get_user_focus_extraction():
    """Verify sector extraction from watchlists."""
    mock_etoro = MagicMock()
    # Mock Watchlist Response
    mock_etoro.get_watchlists.return_value = [
        {
            "Name": "Tech",
            "Items": [
                {"InstrumentDisplayName": "AAPL"},
                {"InstrumentDisplayName": "MSFT"},
                {"InstrumentDisplayName": "GOOGL"}
            ]
        },
        {
            "Name": "Energy",
            "Items": [
                {"InstrumentDisplayName": "XOM"}
            ]
        }
    ]
    
    mock_data = MagicMock()
    # Mock Sector Info
    def get_financials_side_effect(ticker):
        if ticker in ["AAPL", "MSFT", "GOOGL"]:
            return {"sector": "Technology", "industry": "Consumer Electronics"}
        if ticker == "XOM":
            return {"sector": "Energy", "industry": "Oil & Gas"}
        return {}
        
    mock_data.get_financials.side_effect = get_financials_side_effect
    
    service = UserFocusService(user_id="test_user", etoro_service=mock_etoro, market_data_service=mock_data)
    focus = service.get_user_focus(top_n=2)
    
    assert "Technology" in focus["top_sectors"]
    assert "Energy" in focus["top_sectors"]
    assert focus["source_count"] == 4
    # Technology should be first as it has count 3 vs Energy count 1
    assert focus["top_sectors"][0] == "Technology"
