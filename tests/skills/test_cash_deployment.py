import pytest
import json
from unittest.mock import MagicMock, patch
from src.agents.skills.cash_deployment.cli import cash_deployment
from src.domain.trading import Account, BrokerType

@pytest.mark.asyncio
async def test_cash_deployment_balanced():
    """Test where cash ratio is healthy/balanced (below target)."""
    user_id = "test_user_123"
    
    # Mock settings repo
    mock_settings = MagicMock()
    # Mock signature: get(user_id, key, default)
    mock_settings.get.return_value = 0.10 # 10% target
    
    # Mock broker
    mock_broker = MagicMock()
    mock_account = Account(
        broker_type=BrokerType.MOCK,
        account_id="test_acc",
        total_equity=10000.0,
        available_cash=800.0, # 8% < 10%
        currency="USD"
    )
    mock_broker.get_account.return_value = mock_account
    
    with patch("src.agents.skills.cash_deployment.cli.AlchemySettingsRepository", return_value=mock_settings), \
         patch("src.agents.skills.cash_deployment.cli.BrokerFactory.get_broker", return_value=mock_broker):
        
        result_json = await cash_deployment(user_id)
        result = json.loads(result_json)
        
        # Verify
        assert result["status"] == "balanced"
        assert result["excess_cash"] == 0.0
        assert result["cash_ratio"] == 0.08
        assert "healthy" in result["message"]

@pytest.mark.asyncio
async def test_cash_deployment_overweight():
    """Test where cash ratio is high (above target)."""
    user_id = "test_user_123"
    
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.get.return_value = 0.10 # 10% target
    
    # Mock broker
    mock_broker = MagicMock()
    mock_account = Account(
        broker_type=BrokerType.MOCK,
        account_id="test_acc",
        total_equity=10000.0,
        available_cash=3000.0, # 30% > 10%
        currency="USD"
    )
    mock_broker.get_account.return_value = mock_account
    
    with patch("src.agents.skills.cash_deployment.cli.AlchemySettingsRepository", return_value=mock_settings), \
         patch("src.agents.skills.cash_deployment.cli.BrokerFactory.get_broker", return_value=mock_broker):
        
        result_json = await cash_deployment(user_id)
        result = json.loads(result_json)
        
        # Verify
        assert result["status"] == "overweight"
        assert result["excess_cash"] == 2000.0 # 3000 - (10000 * 0.1)
        assert result["cash_ratio"] == 0.30
        assert len(result["candidates"]) > 0
        assert result["candidates"][0]["ticker"] == "VOO"
        assert "Excess cash detected" in result["message"]

@pytest.mark.asyncio
async def test_cash_deployment_no_broker():
    """Test error handling when no broker exists for current context."""
    user_id = "test_user_123"
    
    with patch("src.agents.skills.cash_deployment.cli.BrokerFactory.get_broker", return_value=None):
        result_json = await cash_deployment(user_id)
        result = json.loads(result_json)
        
        assert result["status"] == "error"
        assert "No broker found" in result["error"]

@pytest.mark.asyncio
async def test_cash_deployment_invalid_settings():
    """Test resilience when target_cash_ratio in DB is malformed."""
    user_id = "test_user_123"
    
    mock_settings = MagicMock()
    mock_settings.get.return_value = "invalid_string" # Malformed setting
    
    mock_broker = MagicMock()
    mock_account = Account(
        broker_type=BrokerType.MOCK,
        account_id="test_acc",
        total_equity=10000.0,
        available_cash=3000.0, # 30% > default 10%
        currency="USD"
    )
    mock_broker.get_account.return_value = mock_account
    
    with patch("src.agents.skills.cash_deployment.cli.AlchemySettingsRepository", return_value=mock_settings), \
         patch("src.agents.skills.cash_deployment.cli.BrokerFactory.get_broker", return_value=mock_broker):
        
        result_json = await cash_deployment(user_id)
        result = json.loads(result_json)
        
        # Should fallback to default 0.10 target
        assert result["status"] == "overweight"
        assert result["excess_cash"] == 2000.0
        assert result["target_ratio"] == 0.10
