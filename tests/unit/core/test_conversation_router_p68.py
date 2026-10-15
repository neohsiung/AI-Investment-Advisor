"""
Unit tests for ConversationRouter Section 38 (Phase 68):
Multi-Factor Extreme Stress Testing & Liquidity Squeeze Simulator commands.
"""

import pytest
from unittest.mock import MagicMock
from src.services.conversation_router import ConversationRouter


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_router_handles_stresstest_dashboard():
    """Test /stresstest routes to stress test dashboard."""
    router = ConversationRouter()
    adapter = MagicMock()
    res = await router._handle_system_command(adapter, "chan1", "/stresstest", "user123")
    assert res is not None
    assert "跨市場多因子極端情境壓力測試與流動性擠壓模擬" in res
    assert "四大歷史與合成極端衝擊壓力測試總覽" in res
    assert "資本保全評分" in res


@pytest.mark.anyio
async def test_router_handles_stress_alias():
    """Test /stress alias routes to stress test dashboard."""
    router = ConversationRouter()
    adapter = MagicMock()
    res = await router._handle_system_command(adapter, "chan1", "/stress", "user123")
    assert res is not None
    assert "跨市場多因子極端情境壓力測試與流動性擠壓模擬" in res


@pytest.mark.anyio
async def test_router_handles_chinese_command():
    """Test /壓力測試 routes properly."""
    router = ConversationRouter()
    adapter = MagicMock()
    res = await router._handle_system_command(adapter, "chan1", "/壓力測試", "user123")
    assert res is not None
    assert "跨市場多因子極端情境壓力測試與流動性擠壓模擬" in res


@pytest.mark.anyio
async def test_router_handles_scenario_deep_dive():
    """Test /stresstest covid routes to specific scenario deep-dive."""
    router = ConversationRouter()
    adapter = MagicMock()
    res = await router._handle_system_command(adapter, "chan1", "/stresstest covid", "user123")
    assert res is not None
    assert "極端情境深層穿透剖析" in res
    assert "新冠疫情" in res


@pytest.mark.anyio
async def test_router_handles_summary_parameter():
    """Test /stresstest summary returns overview dashboard."""
    router = ConversationRouter()
    adapter = MagicMock()
    res = await router._handle_system_command(adapter, "chan1", "/stresstest summary", "user123")
    assert res is not None
    assert "四大歷史與合成極端衝擊壓力測試總覽" in res
