import pytest
import anyio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.agents.sentinel import SentinelAgent

@pytest.mark.asyncio
async def test_sentinel_agent_priority_classification():
    """測試 Sentinel Agent 是否能正確從 LLM 輸出解析優先級"""
    # 直接 patch run_tool_loop 避開 LLM Provider 初始化與網路問題
    with patch('src.agents.sentinel.SentinelAgent.run_tool_loop') as mock_call, \
         patch('src.agents.sentinel.SentinelAgent.call_agent', new_callable=AsyncMock) as mock_agent:
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
        result = await agent.run({"trigger_source": "webhook", "event_data": {"ticker": "AAPL"}})
        
        assert result["priority"] == "P2"
        assert result["target_agent"] == "fundamental"

@pytest.mark.asyncio
async def test_sentinel_agent_fallback_on_parse_error():
    """測試當 JSON 解析失敗時，Sentinel Agent 是否能回傳 P2 發布警報"""
    with patch('src.agents.sentinel.SentinelAgent.run_tool_loop') as mock_call:
        mock_call.return_value = "Invalid response without JSON"
        
        agent = SentinelAgent(user_id="test_user")
        result = await agent.run({"event_data": {"unknown": "data"}})
        
        assert result["priority"] == "P2"  # Fallback priority in implementation is P2
        assert "error" in result or "rationale" in result

@pytest.mark.asyncio
async def test_sentinel_agent_with_arbiter_direct():
    """測試 Sentinel Agent 啟用 Arbiter 模式時直接回傳毫秒級強型別結果"""
    mock_arbiter = MagicMock()
    mock_decision = MagicMock()
    mock_decision.choice = "P0"
    mock_decision.confidence = 0.98
    mock_decision.is_escalated = False
    mock_decision.tier = "reflex"
    mock_decision.state_hash = "abc123hash"
    mock_arbiter.decide = AsyncMock(return_value=mock_decision)

    agent = SentinelAgent(user_id="test_user", use_arbiter=True, shadow_mode=False, arbiter_client=mock_arbiter)
    result = await agent.run({"trigger_source": "circuit_breaker", "event_data": {"drop": "7%"}, "current_vix": 38.5})

    assert result["priority"] == "P0"
    assert result["confidence"] == 0.98
    assert result["tier"] == "reflex"
    assert result["is_escalated"] is False
    mock_arbiter.decide.assert_called_once()

