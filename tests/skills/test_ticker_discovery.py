import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.skills.ticker_discovery.impl import ticker_discovery

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_ticker_discovery_success():
    """Test successful discovery and extraction of tickers."""
    user_id = "test_user_123"
    
    # Mock Search Service
    mock_search = AsyncMock()
    mock_search.search_financial_context.return_value = [
        {"title": "Best AI Stocks", "link": "https://example.com/1", "snippet": "NVDA is leading the market, followed by MSFT and AMD."}
    ]
    
    # Mock ResilientLLMPipeline
    mock_pipeline = AsyncMock()
    mock_llm_json = '```json\n[{"ticker": "NVDA", "reason": "GPU Leader", "source": "Web article"}]\n```'
    mock_pipeline.execute.return_value = (mock_llm_json, [])

    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search), \
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[MagicMock()]), \
         patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", return_value=mock_pipeline):
        
        result_json = await ticker_discovery(user_id, strategy="growth")
        result = json.loads(result_json)
        
        assert result["status"] == "success"
        assert len(result["tickers"]) == 1
        assert result["tickers"][0]["ticker"] == "NVDA"
        assert result["tickers"][0]["reason"] == "GPU Leader"

@pytest.mark.anyio
async def test_ticker_discovery_no_results():
    """Test behavior when search returns no results."""
    user_id = "test_user_123"
    
    mock_search = AsyncMock()
    mock_search.search_financial_context.return_value = []
    
    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search):
        result_json = await ticker_discovery(user_id)
        result = json.loads(result_json)
        
        assert result["status"] == "no_results"
        assert result["tickers"] == []

@pytest.mark.anyio
async def test_ticker_discovery_invalid_llm_response():
    """Test resilience against malformed LLM JSON."""
    user_id = "test_user_123"
    
    mock_search = AsyncMock()
    mock_search.search_financial_context.return_value = [{"title": "News", "snippet": "Some text"}]
    
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = ("Non-JSON response text", [])

    with patch("src.agents.skills.ticker_discovery.impl.InternetSearchService", return_value=mock_search), \
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[MagicMock()]), \
         patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", return_value=mock_pipeline):
        
        result_json = await ticker_discovery(user_id)
        result = json.loads(result_json)
        
        assert result["status"] == "parse_error"

