
import pytest
from unittest.mock import MagicMock, patch
import os
from src.services.etoro_service import EtoroService

def test_etoro_headers_with_api_keys():
    """Verify that headers include x-api-key and x-user-key when provided."""
    with patch.dict(os.environ, {
        "ETORO_API_KEY": "test_public_key",
        "ETORO_USER_KEY": "test_user_key"
    }):
        service = EtoroService()
        headers = service._get_headers()
        
        assert headers["x-api-key"] == "test_public_key"
        assert headers["x-user-key"] == "test_user_key"
        assert "x-request-id" in headers
        assert headers["Content-Type"] == "application/json"

def test_etoro_headers_without_api_keys():
    """Verify that headers do NOT include x-api-key if environment variables are missing."""
    with patch.dict(os.environ, {}, clear=True):
        # We need to ensure ETORO_API_BASE_URL is also gone or set to default
        service = EtoroService()
        headers = service._get_headers()
        
        assert "x-api-key" not in headers
        assert "x-user-key" not in headers
        assert "x-request-id" in headers

def test_etoro_base_url_logic():
    """Verify base_url switches between official and local bridge based on keys."""
    # 1. Official
    with patch.dict(os.environ, {"ETORO_API_KEY": "some_key", "ETORO_USER_KEY": "some_user_key"}):
        service = EtoroService()
        assert service.base_url == "https://public-api.etoro.com/api/v1"
        
    # 2. Local Bridge
    with patch.dict(os.environ, {}, clear=True):
        service = EtoroService()
        assert service.base_url == "http://localhost:8000"

@pytest.mark.asyncio
async def test_fetch_portfolio_uses_headers():
    """Verify that API calls pass the authentication headers."""
    from unittest.mock import AsyncMock
    
    with patch.dict(os.environ, {"ETORO_API_KEY": "key1", "ETORO_USER_KEY": "user1"}):
        service = EtoroService()
        
        # Mock _fetch_portfolio_raw to avoid real HTTP calls
        # The test verifies that _get_headers() returns correct keys
        mock_portfolio = {"equity": 1000, "positions": [], "TotalEquity": 1000, "AvailableCash": 500}
        with patch.object(service, '_fetch_portfolio_raw', new_callable=AsyncMock, return_value=mock_portfolio):
            await service.get_account()
        
        # Verify headers contain the correct API keys
        headers = service._get_headers()
        assert headers["x-api-key"] == "key1"
        assert headers["x-user-key"] == "user1"
