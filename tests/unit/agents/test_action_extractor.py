import pytest
import unittest.mock
import json
import asyncio
from src.agents.action_extractor import ActionExtractorAgent

def run_async(coro):
    return asyncio.run(coro)

@pytest.mark.asyncio
async def test_action_extractor_json_block():
    """
    Test parsing of explicit [CONVINCING_ACTION] JSON blocks.
    測試解析明確的 [CONVINCING_ACTION] JSON 區塊。
    """
    mock_content = '''Based on the analysis, we should buy TSLA.
[CONVINCING_ACTION]
[
  {
    "ticker": "TSLA",
    "action": "BUY",
    "quantity": 10,
    "confidence": 9,
    "reason": "Strong momentum and fundamental breakout."
  }
]
[/CONVINCING_ACTION]
The target price is $200.'''
    
    agent = ActionExtractorAgent(tier="fast")
    with unittest.mock.patch.object(agent, 'run_tool_loop', return_value=mock_content):
        result = await agent.run("Dummy council text")
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["action"] == "BUY"
        assert result[0]["quantity"] == 10
        assert result[0]["confidence"] == 9
        assert "Strong momentum" in result[0]["reason"]

@pytest.mark.asyncio
async def test_action_extractor_unstructured_chinese():
    """
    Test parsing of unstructured Chinese text.
    測試解析非結構化中文文字。
    """
    mock_content = '[{"ticker": "NVDA", "action": "SELL", "quantity": 5, "confidence": 8, "reason": "漲太高了"}]'
    
    agent = ActionExtractorAgent(tier="fast")
    with unittest.mock.patch.object(agent, 'run_tool_loop', return_value=mock_content):
        result = await agent.run("輝達現在太貴了，建議賣出5股，信心分數8分。")
        
        assert isinstance(result, list)
        assert result[0]["ticker"] == "NVDA"
        assert result[0]["action"] == "SELL"
        assert result[0]["quantity"] == 5
        assert result[0]["confidence"] == 8

@pytest.mark.asyncio
async def test_action_extractor_invalid_output():
    """
    Test handling of invalid or empty LLM output.
    測試處理無效或空的 LLM 輸出。
    """
    mock_content = "I don't know what to do."
    
    agent = ActionExtractorAgent(tier="fast")
    with unittest.mock.patch.object(agent, 'run_tool_loop', return_value=mock_content):
        result = await agent.run("Garbage input")
        
        assert isinstance(result, list)
        assert len(result) == 0
