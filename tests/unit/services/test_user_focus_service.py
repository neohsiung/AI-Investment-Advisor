import pytest
from unittest.mock import MagicMock, AsyncMock
from src.services.user_focus_service import UserFocusService

@pytest.mark.asyncio
async def test_get_user_focus_empty():
    """Verify empty result when no watchlists."""
    mock_etoro = MagicMock()
    mock_etoro.get_watchlists = AsyncMock(return_value=[])

    service = UserFocusService(user_id="test_user", etoro_service=mock_etoro)
    focus = await service.get_user_focus()
    assert focus == {}

@pytest.mark.asyncio
async def test_get_user_focus_extraction():
    """Verify sector extraction from watchlists."""
    mock_etoro = MagicMock()
    # Mock Watchlist Response
    mock_etoro.get_watchlists = AsyncMock(return_value=[
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
    ])

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
    focus = await service.get_user_focus(top_n=2)

    assert "Technology" in focus["top_sectors"]
    assert "Energy" in focus["top_sectors"]
    assert focus["source_count"] == 4
    # Technology should be first as it has count 3 vs Energy count 1
    assert focus["top_sectors"][0] == "Technology"

@pytest.mark.asyncio
async def test_get_user_focus_awaits_get_watchlists():
    """
    2026-08-26: get_user_focus was sync while EtoroService.get_watchlists is
    async, so the coroutine was never awaited. The resulting
    "'coroutine' object has no attribute 'get'" was swallowed by the blanket
    except Exception, leaving user focus permanently empty in prod.
    """
    mock_etoro = MagicMock()
    mock_etoro.get_watchlists = AsyncMock(return_value=[
        {"Items": [{"InstrumentDisplayName": "AAPL"}]}
    ])

    mock_data = MagicMock()
    mock_data.get_financials.return_value = {"sector": "Technology", "industry": "Consumer Electronics"}

    service = UserFocusService(user_id="test_user", etoro_service=mock_etoro, market_data_service=mock_data)
    focus = await service.get_user_focus()

    mock_etoro.get_watchlists.assert_awaited_once()
    assert focus["top_sectors"] == ["Technology"]
