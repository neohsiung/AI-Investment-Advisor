import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.agents.swarm.fundamental_swarm import FundamentalSwarm
from src.agents.swarm.momentum_swarm import MomentumSwarm
from src.agents.swarm.sentiment_swarm import SentimentSwarm

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_fundamental_swarm_run():
    # FundamentalSwarm uses SupplyChainService
    with patch('src.agents.swarm.fundamental_swarm.SupplyChainService') as MockSC:
        mock_sc = MockSC.return_value
        mock_sc.get_shortage_premium.return_value = {"narrative": "Low supply"}
        
        swarm = FundamentalSwarm(user_id="test_user")
        # RoleSwarm.run calls orchestrator.broadcast
        swarm.orchestrator = MagicMock()
        swarm.orchestrator.broadcast = AsyncMock(return_value={"expert": "Financials are good."})
        swarm.orchestrator.aggregate_results.return_value = "Financials are good."
        
        context = {
            "tickers": ["AAPL"],
            "market_data": {
                "AAPL": {"financials": {}, "news": []}
            }
        }
        res = await swarm.run(context)
        assert "AAPL" in res
        assert "Financials are good" in res

@pytest.mark.anyio
async def test_momentum_swarm_run():
    swarm = MomentumSwarm(user_id="test_user")
    # MomentumSwarm calls orchestrator.batch_run explicitly
    swarm.orchestrator = MagicMock()
    swarm.orchestrator.batch_run = AsyncMock(return_value={"scanner": "Momentum is strong."})
    swarm.orchestrator.aggregate_results.return_value = "Momentum is strong."
    
    context = {"ticker": "NVDA", "indicators": {"RSI": 75}}
    res = await swarm.run(context)
    assert "Momentum is strong" in res

@pytest.mark.anyio
async def test_sentiment_swarm_run():
    swarm = SentimentSwarm(user_id="test_user")
    # SentimentSwarm calls super().run() which is RoleSwarm.run() -> calls broadcast
    swarm.orchestrator = MagicMock()
    swarm.orchestrator.broadcast = AsyncMock(return_value={"pulse": "Sentiment is bullish."})
    swarm.orchestrator.aggregate_results.return_value = "Sentiment is bullish."
    
    context = {
        "tickers": ["TSM"],
        "market_data": {
            "TSM": {"news": [{"title": "Growth"}], "price_change_percent": 5.0}
        }
    }
    
    res = await swarm.run(context)
    assert "TSM" in res
    assert "Sentiment is bullish" in res

@pytest.mark.anyio
async def test_sentiment_no_news():
    swarm = SentimentSwarm(user_id="test_user")
    context = {"tickers": ["TSM"], "market_data": {"TSM": {"news": []}}}
    res = await swarm.run(context)
    assert "Neutral (No News)" in res
