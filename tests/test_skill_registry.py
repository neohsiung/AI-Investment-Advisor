import pytest
from unittest.mock import MagicMock, patch
from src.agents.skills.registry import search_web, get_market_data, get_portfolio, bind_skills_to_agent, SKILL_IMPLEMENTATIONS

@patch('src.agents.skills.registry.get_search_service')
def test_search_web(mock_get_svc):
    """Test search_web function."""
    mock_svc = MagicMock()
    mock_get_svc.return_value = mock_svc
    
    # Setup mock results
    mock_svc.search_financial_context.return_value = [
        {"title": "Result 1", "snippet": "Snippet 1", "link": "http://example.com/1"},
        {"title": "Result 2", "snippet": "Snippet 2", "link": "http://example.com/2"}
    ]
    
    result = search_web("query")
    
    assert "Result 1" in result
    assert "Snippet 1" in result
    assert "http://example.com/1" in result
    
    # Test Empty
    mock_svc.search_financial_context.return_value = []
    assert search_web("empty") == "No results found."
    
    # Test Exception
    mock_svc.search_financial_context.side_effect = Exception("Search Failed")
    assert "Error: Search Failed" in search_web("fail")

@patch('src.agents.skills.registry.get_market_service')
def test_get_market_data(mock_get_svc):
    """Test get_market_data function."""
    mock_svc = MagicMock()
    mock_get_svc.return_value = mock_svc
    
    # Setup mock context
    mock_svc.get_market_context.return_value = {
        "AAPL": {
            "price_data": {"close": [150.0]},
            "indicators": {"RSI": 50}
        }
    }
    
    result = get_market_data("AAPL")
    
    assert "Price: 150.0" in result
    assert "Indicators: {'RSI': 50}" in result
    
    # Test Missing
    mock_svc.get_market_context.return_value = {}
    assert get_market_data("GOOG") == "No data found." # Based on code analysis, if key missing, it returns 'No data found.'? No, code says: if exclude_ticker := context.get(ticker): ... else: return None? No implicit None return usually.
    # Code:
    # context = svc.get_market_context([ticker], enrich=False)
    # if exclude_ticker := context.get(ticker):
    #    ...
    # return "No data found."  <-- Wait, line 63 is outside the if? No, indented?
    # Let's check indentation in view_file.
    
    # Test Exception
    mock_svc.get_market_context.side_effect = Exception("API Error")
    assert "Error: API Error" in get_market_data("ERR")

@patch('src.agents.skills.registry.get_tx_repo')
def test_get_portfolio(mock_get_repo):
    """Test get_portfolio function."""
    mock_repo = MagicMock()
    mock_get_repo.return_value = mock_repo
    
    mock_repo.get_holdings_summary.return_value = "AAPL: 10 shares"
    mock_repo.get_latest_leverage.return_value = 1.05
    
    result = get_portfolio("user123")
    
    assert "Leverage: 1.05" in result
    assert "Holdings: AAPL: 10 shares" in result
    
    # Test Exception
    mock_repo.get_holdings_summary.side_effect = Exception("DB Error")
    assert "Error: DB Error" in get_portfolio("user_err")

def test_bind_skills_to_agent():
    """Test binding logic."""
    mock_agent = MagicMock()
    
    # Mock skill_loader
    mock_loader = MagicMock()
    mock_skill_def = MagicMock()
    mock_skill_def.description = "Test Description"
    mock_loader.skills = {
        "search_web": mock_skill_def,
        "unknown_skill": mock_skill_def
    }
    mock_agent.skill_loader = mock_loader
    
    bind_skills_to_agent(mock_agent)
    
    # Should bind search_web because it is in SKILL_IMPLEMENTATIONS
    mock_agent.register_tool.assert_called()
    
    # Verify McpTool argument
    args = mock_agent.register_tool.call_args
    tool = args[0][0]
    assert tool.name == "search_web"
    assert tool.description == "Test Description"
    assert tool.func == SKILL_IMPLEMENTATIONS["search_web"]
