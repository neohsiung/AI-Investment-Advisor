import pytest
from unittest.mock import MagicMock
from src.services.conversation_router import ConversationRouter

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_router_attribution_command_default():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /attribution returns Phase 66 Factor Orthogonal Residual Attribution Card
    res = await router._handle_system_command(adapter, "chan1", "/attribution", "test_user_p66")
    assert res is not None
    assert "投組多因子正交殘差收益歸因儀表" in res
    assert "多因子施密特正交分解" in res
    assert "純特異超額 Alpha" in res
    assert "市場大盤" in res

@pytest.mark.anyio
async def test_router_attribution_command_with_lookback():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /attribution 30 passes lookback 30
    res = await router._handle_system_command(adapter, "chan1", "/attribution 30", "test_user_p66")
    assert res is not None
    assert "投組多因子正交殘差收益歸因儀表" in res
    assert "近 `30` 個交易日" in res

@pytest.mark.anyio
async def test_router_factor_attribution_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /factor attribution routes properly
    res = await router._handle_system_command(adapter, "chan1", "/factor attribution", "test_user_p66")
    assert res is not None
    assert "投組多因子正交殘差收益歸因儀表" in res

@pytest.mark.anyio
async def test_router_decay_board_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /decay returns Factor Decay and Half-life Board
    res = await router._handle_system_command(adapter, "chan1", "/decay", "test_user_p66")
    assert res is not None
    assert "量化多因子風險衰減與半衰期監控看板" in res
    assert "半衰期" in res
    assert "動態調倉與權重防守建議" in res
    assert "滾動 IC" in res

@pytest.mark.anyio
async def test_router_factor_decay_command():
    router = ConversationRouter()
    adapter = MagicMock()

    # Test /factor decay returns Factor Decay and Half-life Board
    res = await router._handle_system_command(adapter, "chan1", "/factor decay", "test_user_p66")
    assert res is not None
    assert "量化多因子風險衰減與半衰期監控看板" in res

def test_router_is_system_command_p66():
    router = ConversationRouter()
    assert router._is_system_command("/attribution") is True
    assert router._is_system_command("/attribution 30") is True
    assert router._is_system_command("/factor attribution") is True
    assert router._is_system_command("/decay") is True
    assert router._is_system_command("/factor decay") is True
    assert router._is_system_command("/halflife") is True
    assert router._is_system_command("收益歸因") is True
    assert router._is_system_command("因子衰減") is True
    assert router._is_system_command("半衰期") is True
