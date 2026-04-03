import pytest
from unittest.mock import MagicMock, patch
from src.services.token_logger_service import TokenLoggerService

@pytest.fixture
def mock_engine():
    return MagicMock()

@pytest.fixture
def token_logger_service(mock_engine):
    # If the service already took an engine in __init__, we need to ensure the mock is used.
    # The current TokenLoggerService implementation (from previous turn) uses get_db_engine() internally.
    with patch("src.services.token_logger_service.get_db_engine", return_value=mock_engine):
        return TokenLoggerService()

def test_log_usage_calculates_cost(token_logger_service, mock_engine):
    mock_conn = mock_engine.connect.return_value.__enter__.return_value
    
    result = token_logger_service.log_usage(
        user_id="user@example.com",
        agent_name="TestAgent",
        tier="fast",
        model="gpt-4o-mini",
        provider="OpenRouter",
        prompt_tokens=10000,
        completion_tokens=5000
    )
    
    assert result is True
    mock_conn.execute.assert_called_once()
    
    # Check cost calculation logic
    args, kwargs = mock_conn.execute.call_args
    params = args[1]
    
    # TierConfig: fast (input=0.30, output=2.50 per $1M tokens)
    expected_cost = (10000 / 1_000_000 * 0.30) + (5000 / 1_000_000 * 2.50)
    assert pytest.approx(params["total_cost"], rel=1e-6) == expected_cost

def test_get_user_spending_success(token_logger_service, mock_engine):
    mock_conn = mock_engine.connect.return_value.__enter__.return_value
    mock_result = mock_conn.execute.return_value
    
    # Simulate rows returned from SQL: (total_cost, total_tokens, tier, call_count)
    mock_result.fetchall.return_value = [
        MagicMock(total_cost=0.5, total_tokens=1000, tier="smart", call_count=5),
        MagicMock(total_cost=0.1, total_tokens=2000, tier="fast", call_count=10)
    ]
    
    summary = token_logger_service.get_user_spending("test_user", days=7)
    
    assert summary["total_cost"] == 0.6
    assert summary["total_tokens"] == 3000
    assert "smart" in summary["tiers"]
    assert summary["tiers"]["smart"]["cost"] == 0.5
    assert summary["tiers"]["fast"]["calls"] == 10

def test_get_user_spending_empty(token_logger_service, mock_engine):
    mock_conn = mock_engine.connect.return_value.__enter__.return_value
    mock_result = mock_conn.execute.return_value
    mock_result.fetchall.return_value = []
    
    summary = token_logger_service.get_user_spending("test_user")
    
    assert summary["total_cost"] == 0.0
    assert summary["total_tokens"] == 0
    assert summary["tiers"] == {}

def test_get_user_spending_error(token_logger_service, mock_engine):
    mock_engine.connect.side_effect = Exception("DB Error")
    
    summary = token_logger_service.get_user_spending("test_user")
    
    # Safe implementation should return zero cost summary on error
    assert summary["total_cost"] == 0.0
    assert summary["total_tokens"] == 0
