"""
Tests for legacy SkillRegistry compatibility.
Updated for Phase 3 refactoring (SkillRegistry class-based, private implementations).
"""

import pytest
from unittest.mock import MagicMock, patch
from src.agents.skills.registry import (
    SkillRegistry,
    bind_skills_to_agent,
    _search_web,
    _get_market_data,
    _get_portfolio,
)


@patch('src.services.search_service.InternetSearchService')
def test_search_web(mock_svc_cls):
    """Test search_web function."""
    mock_svc = MagicMock()
    mock_svc_cls.return_value = mock_svc

    # Setup mock results
    mock_svc.search_financial_context.return_value = [
        {"title": "Result 1", "snippet": "Snippet 1", "link": "http://example.com/1"},
        {"title": "Result 2", "snippet": "Snippet 2", "link": "http://example.com/2"}
    ]

    result = _search_web("test_user", "query")

    assert "Result 1" in result
    assert "Snippet 1" in result
    assert "http://example.com/1" in result

    # Test Empty
    mock_svc.search_financial_context.return_value = []
    assert _search_web("test_user", "empty") == "No results found."

    # Test Exception
    mock_svc.search_financial_context.side_effect = Exception("Search Failed")
    assert "Error: Search Failed" in _search_web("test_user", "fail")


@patch('src.services.market_data_service.MarketDataService')
def test_get_market_data(mock_svc_cls):
    """Test get_market_data function."""
    mock_svc = MagicMock()
    mock_svc_cls.return_value = mock_svc

    # Setup mock context
    mock_svc.get_market_context.return_value = {
        "AAPL": {
            "price_data": {"close": [150.0]},
            "indicators": {"RSI": 50}
        }
    }

    result = _get_market_data("test_user", "AAPL")

    assert "Price: 150.0" in result
    assert "Indicators: {'RSI': 50}" in result

    # Test Missing
    mock_svc.get_market_context.return_value = {}
    assert _get_market_data("test_user", "GOOG") == "No data found."

    # Test Exception
    mock_svc.get_market_context.side_effect = Exception("API Error")
    assert "Error: API Error" in _get_market_data("test_user", "ERR")


@patch('src.repositories.transaction_repository.AlchemyTransactionRepository')
def test_get_portfolio(mock_repo_cls):
    """Test get_portfolio function."""
    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo

    mock_repo.get_holdings_summary.return_value = "AAPL: 10 shares"
    mock_repo.get_latest_leverage.return_value = 1.05

    result = _get_portfolio("user123")

    assert "Leverage: 1.05" in result
    assert "Holdings: AAPL: 10 shares" in result

    # Test Exception
    mock_repo.get_holdings_summary.side_effect = Exception("DB Error")
    assert "Error: DB Error" in _get_portfolio("user_err")


def test_bind_skills_to_agent():
    """Test binding logic via backward-compatible function."""
    mock_agent = MagicMock()

    mock_loader = MagicMock()
    mock_skill_def = MagicMock()
    mock_skill_def.description = "Test Description"
    mock_loader.skills = {
        "search_web": mock_skill_def,
        "unknown_skill": mock_skill_def
    }
    mock_agent.skill_loader = mock_loader

    bind_skills_to_agent(mock_agent)

    # Should bind search_web because it is in builtins
    mock_agent.register_tool.assert_called()

    # Verify McpTool argument — only search_web should be bound, not unknown_skill
    import functools
    tool = mock_agent.register_tool.call_args[0][0]
    assert tool.name == "search_web"
    assert tool.description == "Test Description"
    assert isinstance(tool.func, functools.partial)
