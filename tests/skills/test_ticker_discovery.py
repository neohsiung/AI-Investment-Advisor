import pytest
import json
from unittest.mock import MagicMock, patch
from src.agents.skills.ticker_discovery.impl import ticker_discovery

@pytest.mark.asyncio
async def test_ticker_discovery_success():
    """Test successful discovery and extraction of tickers."""
    user_id = "test_user_123"
    
    # Mock Search Service
    mock_search = MagicMock()
    mock_search.search_financial_context.return_value = [
        {"title": "Best AI Stocks", "link": "https://example.com/1", "snippet": "NVDA is leading the market, followed by MSFT and AMD."}
    ]
    
    # Mock LLM Gateway
    mock_gateway = MagicMock()
    # Return markdown-style JSON to test parsing resilience
    mock_llm_json = '```json\n[{"ticker": "NVDA", "reason": "GPU Leader", "source": "Web article"}]\n```'
    mock_gateway.chat.return_value = mock_llm_json
    
    # Mock Settings Repository
    mock_settings = MagicMock()
    mock_settings.get.return_value = "fake_gemini_key"

    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search), \
         patch("src.agents.skills.ticker_discovery.impl.LLMGatewayFactory.create", return_value=mock_gateway), \
         patch("src.agents.skills.ticker_discovery.impl.AlchemySettingsRepository", return_value=mock_settings):
        
        result_json = await ticker_discovery(user_id, strategy="growth")
        result = json.loads(result_json)
        
        assert result["status"] == "success"
        assert len(result["tickers"]) == 1
        assert result["tickers"][0]["ticker"] == "NVDA"
        assert result["tickers"][0]["reason"] == "GPU Leader"

@pytest.mark.asyncio
async def test_ticker_discovery_no_results():
    """Test behavior when search returns no results."""
    user_id = "test_user_123"
    
    mock_search = MagicMock()
    mock_search.search_financial_context.return_value = []
    
    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search):
        result_json = await ticker_discovery(user_id)
        result = json.loads(result_json)
        
        assert result["status"] == "no_results"
        assert result["tickers"] == []

@pytest.mark.asyncio
async def test_ticker_discovery_invalid_llm_response():
    """Test resilience against malformed LLM JSON."""
    user_id = "test_user_123"
    
    mock_search = MagicMock()
    mock_search.search_financial_context.return_value = [{"title": "News", "snippet": "Some text"}]
    
    mock_gateway = MagicMock()
    mock_gateway.chat.return_value = "Non-JSON response text"
    
    mock_settings = MagicMock()
    mock_settings.get.return_value = "fake_key"

    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search), \
         patch("src.agents.skills.ticker_discovery.impl.LLMGatewayFactory.create", return_value=mock_gateway), \
         patch("src.agents.skills.ticker_discovery.impl.AlchemySettingsRepository", return_value=mock_settings):
        
        result_json = await ticker_discovery(user_id)
        result = json.loads(result_json)
        
        assert result["status"] == "parse_error"
