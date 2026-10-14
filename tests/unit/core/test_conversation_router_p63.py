import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_trend_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /trend NVDA
    res = await router._handle_system_command(adapter, "chan1", "/trend NVDA", "test_user")
    assert res is not None
    assert "遲滯回差帶過濾與大趨勢單向鎖定儀表" in res
    assert "NVDA" in res
    assert "MA20" in res

@pytest.mark.anyio
async def test_router_tranche_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /tranche NVDA
    res = await router._handle_system_command(adapter, "chan1", "/tranche NVDA", "test_user")
    assert res is not None
    assert "做市商摩擦成本與核心/衛星倉位分級儀表" in res
    assert "NVDA" in res
    assert "70% 核心底倉" in res
    assert "30% 衛星波段" in res
