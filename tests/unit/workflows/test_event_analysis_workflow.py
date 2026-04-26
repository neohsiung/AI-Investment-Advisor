import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.workflow_service import EventAnalysisWorkflow

@pytest.mark.asyncio
async def test_event_analysis_workflow_basic():
    """Verify EventAnalysisWorkflow parses event data and runs agents."""
    user_id = "test_user"
    event_source = "tradingview"
    event_data = {
        "ticker": "AAPL",
        "signal": "BUY",
        "msg": "Bullish crossover"
    }
    
    with patch('src.services.workflow_service.MarketDataService') as mock_market, \
         patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock) as mock_llm, \
         patch('src.services.workflow_service.TransactionService') as mock_trans, \
         patch('src.services.automated_trading_service.AutomatedTradingService') as mock_trade:
        
        # Mock Transaction Data
        mock_trans.return_value.get_holdings_map.return_value = {"AAPL": {"quantity": 10}}
        
        # Mock Market Data
        mock_market.return_value.get_market_context.return_value = {
            "AAPL": {"price_data": {"close": 150.0}, "indicators": {}}
        }
        
        # Mock LLM Responses
        def side_effect(agent_name, *args, **kwargs):
            if agent_name == "Momentum": return "STRONG BUY"
            if agent_name == "Sentiment": return "POSITIVE"
            if agent_name == "CIO": return "### AAPL\n**Action**: **BUY**\n**Reason**: Technical breakout"
            return "Mock Response"
        
        mock_llm.side_effect = side_effect
        
        workflow = EventAnalysisWorkflow(user_id, event_source, event_data)
        
        # Run workflow
        result = await workflow.run(dry_run=False)
        
        assert "AAPL" in result
        assert "BUY" in result
        
        # Verify analysis was called
        assert mock_llm.call_count >= 3


