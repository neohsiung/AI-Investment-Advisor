import pytest
from unittest.mock import MagicMock
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_tranche_drift_telemetry():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /tranche NVDA shows Phase 64A drift telemetry & live spread source
    res = await router._handle_system_command(adapter, "chan1", "/tranche NVDA", "test_user")
    assert res is not None
    assert "做市商摩擦成本與核心/衛星倉位分級儀表" in res
    assert "NVDA" in res
    assert "核心/衛星動態漂移自癒監控" in res
    assert "盤口價差來源" in res

@pytest.mark.anyio
async def test_router_tranche_heal_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /tranche heal NVDA
    res = await router._handle_system_command(adapter, "chan1", "/tranche heal NVDA", "test_user")
    assert res is not None
    assert "核心/衛星動態漂移自癒執行報告" in res
    assert "NVDA" in res
    assert "自癒模擬試算" in res
    assert "TRIM_CORE_TO_SATELLITE" in res
    assert "70.0%" in res

@pytest.mark.anyio
async def test_router_tranche_heal_custom_ticker():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /tranche heal TSLA
    res = await router._handle_system_command(adapter, "chan1", "/tranche heal TSLA", "test_user")
    assert res is not None
    assert "核心/衛星動態漂移自癒執行報告" in res
    assert "TSLA" in res

def test_router_is_system_command_p64():
    router = ConversationRouter()
    assert router._is_system_command("/tranche") is True
    assert router._is_system_command("/tranche heal") is True
    assert router._is_system_command("/tranche heal NVDA") is True
    assert router._is_system_command("自癒") is True
    assert router._is_system_command("漂移自癒") is True
