"""
Unit tests for SkillRouter with ArbiterClient.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.skill_router import SkillRouter

@pytest.mark.asyncio
async def test_skill_router_arbiter_matches_price_check():
    mock_arbiter = MagicMock()
    mock_decision = MagicMock()
    mock_decision.choice = "PRICE_CHECK"
    mock_decision.confidence = 0.94
    mock_arbiter.decide = AsyncMock(return_value=mock_decision)

    router = SkillRouter(user_id="test_user", use_arbiter=True, arbiter_client=mock_arbiter)
    
    with patch.object(router, "_run_skill_via_loader", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "TSLA Price: $250.00"
        
        result = await router.route("TSLA quote")
        
        assert result == "TSLA Price: $250.00"
        mock_arbiter.decide.assert_called_once()
        mock_run.assert_called_once_with("get_market_data", {"ticker": "TSLA"}, "TSLA quote")

@pytest.mark.asyncio
async def test_skill_router_arbiter_falls_through_to_swarm_on_complex_request():
    mock_arbiter = MagicMock()
    mock_decision = MagicMock()
    mock_decision.choice = "SWARM"
    mock_decision.confidence = 0.91
    mock_arbiter.decide = AsyncMock(return_value=mock_decision)

    router = SkillRouter(user_id="test_user", use_arbiter=True, arbiter_client=mock_arbiter)
    
    result = await router.route("Should I hedge my NVDA position before the FOMC meeting?")
    assert result is None  # None indicates complex request should fall through to full swarm
    mock_arbiter.decide.assert_called_once()
