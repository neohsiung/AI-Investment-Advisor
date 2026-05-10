import pytest
import json
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.get_all_thresholds.return_value = {
        "allocation_drift_warning": 3.0,
        "allocation_drift_alert": 5.0,
        "allocation_drift_critical": 10.0
    }
    return repo

@pytest.fixture
def mock_market_service():
    service = MagicMock()
    # Mocking get_current_prices as AsyncMock
    service.get_current_prices = AsyncMock(return_value={"AAPL": 150.0, "NVDA": 500.0})
    return service

@pytest.fixture
def mock_tx_service():
    service = MagicMock()
    # Mocking get_active_positions: AAPL at 150 (cost), qty 10 -> market_value 1500
    service.get_active_positions.return_value = [
        {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0, 'market_value': 1500.0}
    ]
    service.get_cash_balance.return_value = 500.0
    return service

@pytest.fixture
def mock_settings_service():
    service = MagicMock()
    # Default target: AAPL 80% (1600/2000), Cash 20% (400/2000)
    service.get_target_allocation.return_value = {
        "AAPL": {"weight": 80.0}
    }
    return service

@pytest.fixture
def sentinel_service(mock_repo, mock_market_service, mock_tx_service, mock_settings_service):
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer"), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        service = SentinelService(
            user_id="test_user",
            repo=mock_repo,
            market_service=mock_market_service,
            transaction_service=mock_tx_service,
            settings_service=mock_settings_service
        )
        return service

@pytest.mark.asyncio
async def test_no_drift_when_target_allocation_empty(sentinel_service, mock_settings_service):
    mock_settings_service.get_target_allocation.return_value = {}
    triggers = await sentinel_service._check_allocation_drift()
    assert len(triggers) == 0

@pytest.mark.asyncio
async def test_no_drift_when_within_threshold(sentinel_service, mock_tx_service, mock_market_service, mock_settings_service):
    # Total = 1500 (AAPL) + 500 (Cash) = 2000
    # AAPL Weight = 1500/2000 = 75%
    # Target = 77% (Drift = 2%, below warning 3%)
    mock_settings_service.get_target_allocation.return_value = {"AAPL": {"weight": 77.0}}
    triggers = await sentinel_service._check_allocation_drift()
    assert len(triggers) == 0

@pytest.mark.asyncio
async def test_warning_level_drift_no_trigger(sentinel_service, mock_settings_service):
    # AAPL Weight = 75%
    # Target = 71% (Drift = 4%, above warning 3% but below alert 5%)
    mock_settings_service.get_target_allocation.return_value = {"AAPL": {"weight": 71.0}}
    triggers = await sentinel_service._check_allocation_drift()
    # Warning only logs, doesn't append to triggers
    assert len(triggers) == 0

@pytest.mark.asyncio
async def test_alert_level_drift(sentinel_service, mock_settings_service):
    # v10.1 Concentration-Risk Model:
    # AAPL weight = 1500/(1500+500) = 75%
    # max_single_position_weight = 70% → AAPL (75%) exceeds limit → critical trigger
    mock_settings_service.get_setting.return_value = 70.0
    with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService",
               side_effect=Exception("mocked")):
        triggers = await sentinel_service._check_allocation_drift()

    assert len(triggers) == 1
    assert triggers[0]['severity'] == 'critical'
    assert triggers[0]['trigger_type'] == 'allocation_drift'
    assert "AAPL" in triggers[0]['text']

@pytest.mark.asyncio
async def test_critical_level_drift(sentinel_service, mock_settings_service):
    # AAPL weight = 75%, max_single_position_weight = 70% → critical rebalance action
    mock_settings_service.get_setting.return_value = 70.0
    with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService",
               side_effect=Exception("mocked")):
        triggers = await sentinel_service._check_allocation_drift()

    assert len(triggers) == 1
    assert triggers[0]['severity'] == 'critical'
    assert triggers[0]['action'] == 'trigger_rebalance'

@pytest.mark.asyncio
async def test_multiple_tickers_drift(sentinel_service, mock_tx_service, mock_market_service, mock_settings_service):
    # AAPL: qty 10, price 150 → 1500; NVDA: qty 1, price 500 → 500; Cash: 500
    # Total = 2500; AAPL weight = 60%; NVDA weight = 20%
    # max_single_position_weight = 50% → AAPL (60%) triggers, NVDA (20%) does not
    mock_tx_service.get_active_positions.return_value = [
        {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0},
        {'ticker': 'NVDA', 'quantity': 1, 'avg_price': 500.0}
    ]
    mock_market_service.get_current_prices.return_value = {"AAPL": 150.0, "NVDA": 500.0}
    mock_settings_service.get_setting.return_value = 50.0

    with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService",
               side_effect=Exception("mocked")):
        triggers = await sentinel_service._check_allocation_drift()

    assert len(triggers) == 1
    assert "AAPL" in triggers[0]['id']
    assert "NVDA" not in str(triggers)

