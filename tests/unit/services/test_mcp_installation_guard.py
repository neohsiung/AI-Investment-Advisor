import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.mcp_installation_guard import MCPBackgroundCheckService

@pytest.fixture
def guard():
    return MCPBackgroundCheckService(user_id="test_user")

def test_verify_security_clearance_safe_code(guard):
    """測試安全程式碼能通過檢查。"""
    safe_code = """
def calculate_roi(investment, return_val):
    if investment == 0:
        return 0
    return (return_val - investment) / investment
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(safe_code)
        tmp_path = tmp.name
    
    try:
        is_safe, reason = guard.verify_security_clearance(tmp_path)
        assert is_safe is True
        assert "PASSED" in reason
    finally:
        os.unlink(tmp_path)

@pytest.mark.parametrize("malicious_code, expected_reason", [
    ("eval('1+1')", "eval"),
    ("exec('import os')", "exec"),
    ("__import__('os').system('ls')", "__import__"),
    ("import os\nos.system('ls')", "Importing dangerous module 'os'"),
    ("from subprocess import run\nrun(['ls'])", "Importing from dangerous module 'subprocess'"),
    ("import socket\ns = socket.socket()", "Importing dangerous module 'socket'"),
    ("import requests\nrequests.get('http://evil.com')", "Importing dangerous module 'requests'"),
])
def test_verify_security_clearance_malicious_code(guard, malicious_code, expected_reason):
    """測試惡意程式碼會被阻擋。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(malicious_code)
        tmp_path = tmp.name
    
    try:
        is_safe, reason = guard.verify_security_clearance(tmp_path)
        assert is_safe is False
        assert expected_reason in reason
    finally:
        os.unlink(tmp_path)

@patch("src.services.settings_service.SettingsService.get_all_settings")
@patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create")
@pytest.mark.asyncio
async def test_verify_purpose_alignment_approve(mock_gateway_create, mock_get_settings, guard):
    """測試用途對齊審核通過。"""
    mock_get_settings.return_value = {
        "AI_PROVIDER": "MockProvider",
        "AI_MODEL_FAST": "mock-model",
        "API_KEY": "mock-key"
    }
    
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Decision: APPROVE\nReason: Fits intent."
    mock_gateway_create.return_value = mock_llm
    
    is_aligned, reason = await guard.verify_purpose_alignment(
        "get_stock_price", "Fetch current price", "I want to see market data"
    )
    
    assert is_aligned is True
    assert "PASSED" in reason

@patch("src.services.settings_service.SettingsService.get_all_settings")
@patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create")
@pytest.mark.asyncio
async def test_verify_purpose_alignment_reject(mock_gateway_create, mock_get_settings, guard):
    """測試用途對齊審核拒絕。"""
    mock_get_settings.return_value = {
        "AI_PROVIDER": "MockProvider",
        "API_KEY": "mock-key"
    }
    
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Decision: REJECT\nReason: Tool intent mismatch."
    mock_gateway_create.return_value = mock_llm
    
    is_aligned, reason = await guard.verify_purpose_alignment(
        "buy_coffee", "Order coffee", "I want to analyze my portfolio"
    )
    
    assert is_aligned is False
    assert "Purpose Mismatch" in reason
    assert "Tool intent mismatch" in reason
