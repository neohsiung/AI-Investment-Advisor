import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta

from src.services.automated_trading_service import AutomatedTradingService
from src.services.interaction_service import InteractionService
from src.infrastructure.nlp.intent_classifier import IntentClassifier
from src.domain.trading import Order, OrderAction
from src.domain.interaction import InteractionStatus

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_trade_approval_with_ok_reply(anyio_backend):
    """
    Test that replying "OK" to a trade approval request triggers execution.
    測試對交易審核請求回覆 "OK" 會觸發執行。
    """
    user_id = "test_user@example.com"
    ticker = "AAPL"
    
    # 1. Mock Dependencies
    mock_settings_repo = MagicMock()
    # Upper threshold = 9, Min threshold = 3
    mock_settings_repo.get.side_effect = lambda uid, key, default=None: {
        "ai_trading_enabled": "true",
        "auto_trade_threshold": 9,
        "auto_trade_min_threshold": 3
    }.get(key, default)
    
    mock_broker = MagicMock()
    mock_broker.get_name.return_value = "MockBroker"
    mock_broker.execute_order.return_value = {"status": "success", "order_id": "12345"}
    
    # 2. Setup Services
    # We need a real InteractionService to handle the text response logic
    # but with mocked adapters and classifier
    mock_adapter = AsyncMock()
    mock_adapter.__class__.__name__ = "MockAdapter"
    
    # We will mock AgentFactory to avoid real LLM calls during test
    with patch("src.agents.factory.AgentFactory.create_agent") as mock_create:
        mock_agent = MagicMock()
        mock_create.return_value = mock_agent
        classifier = IntentClassifier()
    
        classifier = IntentClassifier()
    
    interaction_svc = InteractionService(adapters=[mock_adapter], intent_classifier=classifier, settings_service=MagicMock())
    # Mock settings_service.find_user_by_channel_id to return our user_id
    interaction_svc.settings_service.find_user_by_channel_id.return_value = user_id
    
    trade_svc = AutomatedTradingService(
        settings_repo=mock_settings_repo,
        interaction_service=interaction_svc
    )
    
    # 3. Trigger Trade Evaluation (Score 7 is between 3 and 9)
    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker):
        # Start evaluation in a task because it will block waiting for approval
        trade_task = asyncio.create_task(trade_svc.evaluate_and_execute_trade(
            user_id=user_id,
            ticker=ticker,
            action="BUY",
            quantity=10,
            confidence_score=7,
            rationale="Strong signal detected"
        ))
        
        # Give it a moment to send the request
        await asyncio.sleep(0.1)
        
        # 4. Verify Request was sent
        assert len(interaction_svc._pending_requests) == 1
        req_id = list(interaction_svc._pending_requests.keys())[0]
        req = interaction_svc._pending_requests[req_id]
        assert req.status == InteractionStatus.PENDING
        
        # 5. Simulate "OK" response from user
        # This calls handles_text_response which uses IntentClassifier
        # We need to ensure IntentClassifier is updated to handle "OK"
        await interaction_svc.handle_text_response(mock_adapter, "channel_user_123", "OK")
        
        # Wait for the trade task to complete
        result = await trade_task
        
        # 6. Final Assertions
        assert result["status"] == "success"
        mock_broker.execute_order.assert_called_once()
        order = mock_broker.execute_order.call_args[0][0]
        assert order.symbol == ticker
        assert order.action == OrderAction.BUY
        
        # Verify req status updated
        assert req.status == InteractionStatus.APPROVED
