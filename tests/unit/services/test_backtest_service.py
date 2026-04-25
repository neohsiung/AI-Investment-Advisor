import pytest
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import pandas as pd
from src.services.backtest_service import BacktestService
from src.domain.entities import SecurityContext

@pytest.fixture
def mock_feedback_repo():
    return MagicMock()

@pytest.fixture
def mock_yf_data():
    dates = pd.date_range("2024-01-01", periods=60)
    data = {"Close": [150.0 + i for i in range(60)]}
    return pd.DataFrame(data, index=dates)

@pytest.fixture
def mock_model_router():
    router = MagicMock()
    router.get_model = MagicMock(return_value="meta-llama/llama-2-70b-chat")
    return router

@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.chat = AsyncMock(return_value="This looks promising. BUY AAPL.")
    return gateway

@pytest.mark.asyncio
async def test_backtest_simulation_flow_pad_phase2(mock_feedback_repo, mock_yf_data, mock_model_router, mock_gateway):
    # Mock yfinance
    with patch("src.services.backtest_service.yf.download", return_value=mock_yf_data) as mock_yf:
        # Mock SettingsAwareModelRouter and OpenRouterGateway (PAD Phase 2)
        with patch("src.services.backtest_service.SettingsAwareModelRouter") as mock_router_class:
            mock_router_class.return_value = mock_model_router
            
            with patch("src.services.backtest_service.OpenRouterGateway") as mock_gateway_class:
                mock_gateway_class.return_value = mock_gateway
                
                service = BacktestService(feedback_repo=mock_feedback_repo, user_id="test_user")
                await service.run_simulation("AAPL", days_back=10)
                
                # Checks
                assert mock_yf.called
                # We expect save to be called for each valid day (roughly 10 - 5 (T+5 buffer) days) 
                # Logic: loop range(len-15, len-5) -> 10 iterations.
                assert mock_feedback_repo.save.call_count > 0
                
                # Verify passed object
                args = mock_feedback_repo.save.call_args[0]
                example = args[0]
                assert example.agent_name == "Momentum"
                assert example.signal.value == "BUY"
                
                # Verify gateway was called
                assert mock_gateway.chat.called
