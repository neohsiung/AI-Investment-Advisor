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

@pytest.mark.asyncio
async def test_backtest_simulation_flow(mock_feedback_repo, mock_yf_data):
    # Mock yfinance
    with patch("src.services.backtest_service.yf.download", return_value=mock_yf_data) as mock_yf:
        # Mock Agent
        with patch("src.services.backtest_service.AgentFactory.create_agent") as mock_factory:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value="This looks promising. BUY AAPL.")
            mock_factory.return_value = mock_agent

            service = BacktestService(feedback_repo=mock_feedback_repo)
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
