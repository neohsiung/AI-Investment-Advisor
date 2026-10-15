import pytest
from unittest.mock import MagicMock
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_rebalance_command_default():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /rebalance returns Phase 67 Tactical Decay Rebalancing Dashboard
    res = await router._handle_system_command(adapter, "chan1", "/rebalance", "test_user_p67")
    assert res is not None
    assert "戰術因子衰減自適應調倉儀表" in res
    assert "因子衰減前後權重對比" in res
    assert "建議調倉操作名冊" in res
    assert "剛性防守現金儲備" in res

@pytest.mark.anyio
async def test_router_rebalance_plan_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /rebalance plan returns execution plan with shares
    res = await router._handle_system_command(adapter, "chan1", "/rebalance plan", "test_user_p67")
    assert res is not None
    assert "戰術因子衰減調倉執行方案" in res

@pytest.mark.anyio
async def test_router_factor_rebalance_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /factor rebalance routes to Phase 67
    res = await router._handle_system_command(adapter, "chan1", "/factor rebalance", "test_user_p67")
    assert res is not None
    assert "戰術因子衰減自適應調倉儀表" in res

@pytest.mark.anyio
async def test_router_decay_rebalance_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /decay rebalance routes to Phase 67
    res = await router._handle_system_command(adapter, "chan1", "/decay rebalance", "test_user_p67")
    assert res is not None
    assert "戰術因子衰減自適應調倉儀表" in res

def test_router_is_system_command_p67():
    router = ConversationRouter()
    assert router._is_system_command("/rebalance") is True
    assert router._is_system_command("/rebalance plan") is True
    assert router._is_system_command("/factor rebalance") is True
    assert router._is_system_command("/decay rebalance") is True
    assert router._is_system_command("/tactical rebalance") is True
    assert router._is_system_command("調倉") is True
    assert router._is_system_command("自適應調倉") is True
    assert router._is_system_command("衰減調倉") is True
    assert router._is_system_command("因子調倉") is True
