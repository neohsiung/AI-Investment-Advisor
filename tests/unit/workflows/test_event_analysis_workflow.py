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
@pytest.mark.asyncio
async def test_event_analysis_workflow_noise_dropped():
    """Verify low-signal noise/PR is dropped at Stage 1/2 with 0 LLM calls."""
    user_id = "test_user"
    event_source = "rss"
    event_data = {
        "ticker": "GLOBAL",
        "msg": "PR Newswire: Best 5 tips to save money and buy laptops on sale",
        "url": "https://example.com/pr/123",
    }

    with patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock) as mock_llm, \
         patch('src.services.workflow_service.BaseWorkflow.distribute_report', new_callable=AsyncMock) as mock_distribute, \
         patch('src.services.workflow_service.TransactionService') as mock_trans:

        mock_trans.return_value.get_holdings_map.return_value = {"TSM": {"quantity": 5}}

        workflow = EventAnalysisWorkflow(user_id, event_source, event_data)
        result = await workflow.run(dry_run=False)

        assert "Dropped" in result
        mock_llm.assert_not_called()
        mock_distribute.assert_not_called()


@pytest.mark.asyncio
async def test_event_analysis_workflow_non_actionable_suppresses_notification():
    """Verify non-actionable intelligence is saved to DB but notifications suppressed."""
    user_id = "test_user"
    event_source = "rss"
    event_data = {
        "ticker": "TSM",
        "msg": "TSM reports steady monthly sales aligned with consensus guidance",
        "url": "https://reuters.com/tsm-sales",
    }

    with patch('src.services.workflow_service.MarketDataService') as mock_market, \
         patch('src.services.workflow_service.BaseWorkflow._call_agent_llm', new_callable=AsyncMock) as mock_llm, \
         patch('src.services.workflow_service.BaseWorkflow.distribute_report', new_callable=AsyncMock) as mock_distribute, \
         patch('src.services.workflow_service.TransactionService') as mock_trans:

        mock_trans.return_value.get_holdings_map.return_value = {"TSM": {"quantity": 10, "avg_price": 160.0}}
        mock_market.return_value.get_market_context.return_value = {
            "TSM": {"price_data": {"close": 170.0}, "indicators": {}}
        }

        def side_effect(agent_name, *args, **kwargs):
            if agent_name == "Momentum": return "NEUTRAL"
            if agent_name == "Sentiment": return "NEUTRAL"
            if agent_name == "CIO": return "### TSM\n**Action**: **HOLD**\n**Reason**: Fundamental thesis unchanged"
            return "Mock"

        mock_llm.side_effect = side_effect

        workflow = EventAnalysisWorkflow(user_id, event_source, event_data)
        result = await workflow.run(dry_run=False)

        assert "TSM" in result
        assert "HOLD" in result

        # Verify distribute_report was called with dispatch_notifications=False
        mock_distribute.assert_called_once()
        _, kwargs = mock_distribute.call_args
        assert kwargs["dispatch_notifications"] is False
        assert kwargs["report_type"] == "MarketIntelligence"



