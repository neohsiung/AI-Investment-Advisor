import pytest
import unittest.mock
import json
import os
from src.agents.skills.extract_actions.impl import extract_actions

@pytest.mark.asyncio
async def test_extract_actions_json_block():
    """Test parsing of explicit JSON blocks in the skill."""
    mock_content = '''Based on the analysis, we should buy TSLA.
[
  {
    "ticker": "TSLA",
    "action": "BUY",
    "quantity": 10,
    "confidence": 9,
    "reason": "Strong momentum and fundamental breakout."
  }
]
The target price is $200.'''
    
    # Mock LLM and Settings
    mock_gateway = unittest.mock.AsyncMock()
    mock_gateway.chat.return_value = mock_content
    
    with unittest.mock.patch('src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create', return_value=mock_gateway), \
         unittest.mock.patch('src.repositories.settings_repository.AlchemySettingsRepository.get', return_value="dummy_key"):
        
        result_json = await extract_actions("test_user", "Dummy council text")
        result = json.loads(result_json)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["action"] == "BUY"
        assert result[0]["quantity"] == 10
        assert result[0]["confidence"] == 9

@pytest.mark.asyncio
async def test_extract_actions_portfolio_context():
    """Test that portfolio context is handled correctly by the skill."""
    mock_content = '[]'
    mock_gateway = unittest.mock.AsyncMock()
    mock_gateway.chat.return_value = mock_content
    
    with unittest.mock.patch('src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create', return_value=mock_gateway), \
         unittest.mock.patch('src.repositories.settings_repository.AlchemySettingsRepository.get', return_value="dummy_key"):
        
        await extract_actions("test_user", "Hold positions", portfolio="TSLA(0.5), NVDA(10)")
        
        # Verify prompt construction (inspecting call args)
        args, kwargs = mock_gateway.chat.call_args
        messages = args[0]
        system_msg = next(m for m in messages if m.role == "system")
        assert "TSLA(0.5)" in system_msg.content
        assert "PORTFOLIO HOLDINGS" in system_msg.content

@pytest.mark.asyncio
async def test_extract_actions_invalid_json():
    """Test handling of invalid LLM JSON response."""
    mock_content = "I don't know what to do."
    mock_gateway = unittest.mock.AsyncMock()
    mock_gateway.chat.return_value = mock_content
    
    with unittest.mock.patch('src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create', return_value=mock_gateway), \
         unittest.mock.patch('src.repositories.settings_repository.AlchemySettingsRepository.get', return_value="dummy_key"):
        
        result_json = await extract_actions("test_user", "Garbage input")
        result = json.loads(result_json)
        
        assert isinstance(result, list)
        assert len(result) == 0
