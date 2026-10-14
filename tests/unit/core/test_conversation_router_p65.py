import pytest
from unittest.mock import MagicMock
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_fx_telemetry_default():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /fx returns Phase 65 FX dashboard
    res = await router._handle_system_command(adapter, "chan1", "/fx", "test_user")
    assert res is not None
    assert "跨市場即時外匯對沖與多幣種保證金流動性儀表" in res
    assert "TWD" in res
    assert "99% 10日 FX VaR" in res
    assert "安全餘裕" in res

@pytest.mark.anyio
async def test_router_fx_telemetry_custom_currency():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /fx EUR returns EUR base currency
    res = await router._handle_system_command(adapter, "chan1", "/fx EUR", "test_user")
    assert res is not None
    assert "EUR" in res
    assert "跨市場即時外匯對沖與多幣種保證金流動性儀表" in res

@pytest.mark.anyio
async def test_router_fx_hedge_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /fx hedge JPY returns hedging action plan
    res = await router._handle_system_command(adapter, "chan1", "/fx hedge JPY", "test_user")
    assert res is not None
    assert "外匯動態避險與利潤結匯執行方案" in res
    assert "JPY" in res
    assert "建議對沖避險額度" in res

def test_router_is_system_command_p65():
    router = ConversationRouter()
    assert router._is_system_command("/fx") is True
    assert router._is_system_command("/fx EUR") is True
    assert router._is_system_command("/fx hedge") is True
    assert router._is_system_command("外匯") is True
    assert router._is_system_command("匯率避險") is True
    assert router._is_system_command("保證金緩衝") is True
