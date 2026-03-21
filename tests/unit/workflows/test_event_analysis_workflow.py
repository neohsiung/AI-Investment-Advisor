import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.services.workflow_service import EventAnalysisWorkflow

def test_event_analysis_workflow_basic():
    """Verify EventAnalysisWorkflow parses event data and runs agents."""
    import asyncio
    
    async def run_test():
        user_id = "test_user"
        event_source = "tradingview"
        event_data = {
            "ticker": "AAPL",
            "signal": "BUY",
            "msg": "Bullish crossover"
        }
        
        with patch('src.services.workflow_service.MarketDataService') as mock_market, \
             patch('src.services.workflow_service.AgentFactory') as mock_factory, \
             patch('src.services.workflow_service.TransactionService') as mock_trans, \
             patch('src.services.automated_trading_service.AutomatedTradingService') as mock_trade:
            
            # Mock Transaction Data
            mock_trans.return_value.get_holdings_map.return_value = {"AAPL": {"quantity": 10}}
            
            # Mock Market Data
            mock_market.return_value.get_market_context.return_value = {
                "AAPL": {"price_data": {"close": 150.0}, "indicators": {}}
            }
            
            # Mock Agents
            mock_mom = MagicMock()
            mock_mom.run.return_value = "STRONG BUY"
            mock_sent = MagicMock()
            mock_sent.run.return_value = "POSITIVE"
            mock_cio = MagicMock()
            mock_cio.run.return_value = "### AAPL\n**Action**: **BUY**\n**Reason**: Technical breakout"
            
            mock_factory.create_momentum_agent.return_value = mock_mom
            mock_factory.create_sentiment_agent.return_value = mock_sent
            mock_factory.create_cio_agent.return_value = mock_cio
            
            workflow = EventAnalysisWorkflow(user_id, event_source, event_data)
            
            # Run workflow
            result = await workflow.run(dry_run=False)
            
            assert "AAPL" in result
            assert "BUY" in result
            
            # Verify analysis was called
            assert mock_mom.run.called
            assert mock_sent.run.called
            assert mock_cio.run.called

    asyncio.run(run_test())
        
        # Verify trade execution was attempted (parsed from CIO report)
        # Note: In the workflow code, _parse_actionable_orders is called
        # We need to ensure the CIO output matches what the parser expects.
        # Check that evaluate_and_execute_trade was called if we mock it right.
        # However, _parse_actionable_orders looks for a table or specific markers.
        # Let's update internal mock report if needed.
