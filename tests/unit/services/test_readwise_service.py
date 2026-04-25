import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, call
from src.services.readwise_service import ReadwiseService
from src.data.providers.readwise_provider import ReadwiseProvider

@pytest.fixture
def mock_settings_service():
    """Mock settings service."""
    instance = MagicMock()
    instance.get_all_settings.return_value = {"READWISE_API_KEY": "fake_key"}
    instance.get_setting.return_value = None
    return instance

def test_readwise_service_parse_json_response():
    """Test JSON response parsing with various formats."""
    with patch("src.services.readwise_service.SettingsService"), \
         patch("src.services.readwise_service.AlchemySettingsRepository"):
        service = ReadwiseService(user_id="test_user")
        
        # Test with valid dict
        result = service._parse_json_response({
            "is_investment_related": True,
            "requires_action": False,
            "reasoning": "test",
            "suggested_action": None
        })
        assert result["is_investment_related"] is True
        
        # Test with JSON string
        result = service._parse_json_response(
            '{"is_investment_related": true, "requires_action": false, "reasoning": "test", "suggested_action": null}'
        )
        assert result["is_investment_related"] is True
        
        # Test with malformed response
        result = service._parse_json_response("some error response")
        assert result["is_investment_related"] is False

def test_readwise_service_analyze_highlight_sync():
    """Test synchronous analyze_highlight wrapper."""
    with patch("src.services.readwise_service.SettingsService") as mock_settings, \
         patch("src.services.readwise_service.AlchemySettingsRepository"), \
         patch("src.services.readwise_service.SettingsAwareModelRouter") as mock_router, \
         patch("src.services.readwise_service.OpenRouterGateway") as mock_gateway:
        
        # Configure mocks
        mock_router_instance = MagicMock()
        mock_router_instance.get_model.return_value = "google/gemini-2.0-flash-exp"
        mock_router.return_value = mock_router_instance
        
        mock_gateway_instance = MagicMock()
        mock_gateway_instance.chat = AsyncMock(
            return_value='{"is_investment_related": true, "requires_action": true, "reasoning": "About AAPL", "suggested_action": "Buy"}'
        )
        mock_gateway.return_value = mock_gateway_instance
        
        settings_instance = MagicMock()
        mock_settings.return_value = settings_instance
        
        service = ReadwiseService(user_id="test_user", settings_service=settings_instance)
        
        # Test analyze_highlight (sync wrapper)
        result = service.analyze_highlight("Always buy low.", book_id="999", note="Good tip")
        
        assert result["is_investment_related"] is True
        assert result["requires_action"] is True

@pytest.mark.asyncio
async def test_readwise_service_analyze_highlight_async():
    """Test async analyze_highlight_async method."""
    with patch("src.services.readwise_service.SettingsService") as mock_settings, \
         patch("src.services.readwise_service.AlchemySettingsRepository"), \
         patch("src.services.readwise_service.SettingsAwareModelRouter") as mock_router, \
         patch("src.services.readwise_service.OpenRouterGateway") as mock_gateway:
        
        # Configure mocks
        mock_router_instance = MagicMock()
        mock_router_instance.get_model.return_value = "google/gemini-2.0-flash-exp"
        mock_router.return_value = mock_router_instance
        
        mock_gateway_instance = MagicMock()
        mock_gateway_instance.chat = AsyncMock(
            return_value='{"is_investment_related": true, "requires_action": true, "reasoning": "About stocks", "suggested_action": "Buy"}'
        )
        mock_gateway.return_value = mock_gateway_instance
        
        settings_instance = MagicMock()
        mock_settings.return_value = settings_instance
        
        service = ReadwiseService(user_id="test_user", settings_service=settings_instance)
        
        result = await service.analyze_highlight_async(
            "Always buy low.",
            book_id="999",
            note="Good tip"
        )
        
        assert result["is_investment_related"] is True
        assert result["requires_action"] is True
        mock_gateway_instance.chat.assert_called_once()

def test_readwise_service_fetch_and_analyze_highlights():
    """Test fetch_and_analyze_highlights with async processing."""
    with patch("src.services.readwise_service.SettingsService") as mock_settings, \
         patch("src.services.readwise_service.AlchemySettingsRepository"), \
         patch("src.services.readwise_service.SettingsAwareModelRouter") as mock_router, \
         patch("src.services.readwise_service.OpenRouterGateway") as mock_gateway, \
         patch.object(ReadwiseProvider, "fetch_highlights") as mock_fetch:
        
        # Configure provider mock
        mock_fetch.return_value = [
            {
                "id": 101,
                "text": "Always buy low.",
                "note": "Good tip",
                "book_id": 999,
                "url": "http://example.com",
                "highlighted_at": "2026-04-21T19:00:00Z"
            }
        ]
        
        # Configure gateway mock
        mock_router_instance = MagicMock()
        mock_router_instance.get_model.return_value = "google/gemini-2.0-flash-exp"
        mock_router.return_value = mock_router_instance
        
        mock_gateway_instance = MagicMock()
        mock_gateway_instance.chat = AsyncMock(
            return_value='{"is_investment_related": true, "requires_action": true, "reasoning": "Investment related", "suggested_action": "Monitor"}'
        )
        mock_gateway.return_value = mock_gateway_instance
        
        settings_instance = MagicMock()
        mock_settings.return_value = settings_instance
        
        service = ReadwiseService(user_id="test_user", settings_service=settings_instance)
        analyzed = service.fetch_and_analyze_highlights()
        
        # Verify results
        assert len(analyzed) == 1
        assert analyzed[0]["id"] == 101
        assert analyzed[0]["text"] == "Always buy low."
        assert analyzed[0]["analysis"]["is_investment_related"] is True
        assert analyzed[0]["analysis"]["requires_action"] is True
        
        # Verify gateway was called
        mock_gateway_instance.chat.assert_called()
