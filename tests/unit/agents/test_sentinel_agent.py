import pytest
import anyio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.agents.sentinel import SentinelAgent

def test_sentinel_agent_priority_classification():
    """測試 Sentinel Agent 是否能正確從 LLM 輸出解析優先級"""
    # 直接 patch call_llm 避開 LLM Provider 初始化與網路問題
    with patch('src.agents.sentinel.SentinelAgent.call_llm') as mock_call:
        mock_call.return_value = """
        Thinking: Analysis of trigger.
        ```json
        {
            "priority": "P2",
            "target_agent": "fundamental",
            "reason": "Important ticker event"
        }
        ```
        """
        
        agent = SentinelAgent(user_id="test_user")
        result = agent.run({"trigger_source": "webhook", "event_data": {"ticker": "AAPL"}})
        
        assert result["priority"] == "P2"
        assert result["target_agent"] == "fundamental"

def test_sentinel_agent_fallback_on_parse_error():
    """測試當 JSON 解析失敗時，Sentinel Agent 是否能回傳 P2 發布警報"""
    with patch('src.agents.sentinel.SentinelAgent.call_llm') as mock_call:
        mock_call.return_value = "Invalid response without JSON"
        
        agent = SentinelAgent(user_id="test_user")
        result = agent.run({"event_data": {"unknown": "data"}})
        
        assert result["priority"] == "P2"  # Fallback priority in implementation is P2
        assert "error" in result or "rationale" in result
