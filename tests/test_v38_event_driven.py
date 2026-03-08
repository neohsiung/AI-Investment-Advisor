import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.sentinel_service import SentinelService
from src.repositories.sentinel_repository import AlchemySentinelRepository

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def mock_sentinel_repo():
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo:
        mock_instance = MagicMock(spec=AlchemySentinelRepository)
        # Mock initial calls in constructor
        mock_instance.engine = MagicMock() # Fix AttributeError: engine
        mock_instance.get_all_thresholds.return_value = {
            "vix_high": 25.0,
            "vix_extreme": 40.0,
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
            "news_risk_score": 0.6
        }
        mock_instance.is_duplicate_alert.return_value = False
        MockRepo.return_value = mock_instance
        yield mock_instance

@pytest.mark.anyio
async def test_sentinel_process_event(mock_sentinel_repo):
    # Setup mocks for services
    mock_council = MagicMock()
    mock_council.start_session = AsyncMock(return_value={"consensus": "⚠️ Sell AAPL immediately"})
    
    # Mock SettingsService for constructor
    with patch('src.services.sentinel_service.SettingsService') as MockSettings, \
         patch('src.services.sentinel_service.MarketDataService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
        
        sentinel = SentinelService(
            council_service=mock_council,
            user_id="test_user",
            repo=mock_sentinel_repo,
            snapshot_repo=MagicMock() # Mock snapshot repo too
        )
        
        # Simulate an event
        event = {
            "source": "mktrecap",
            "data": {
                "ticker": "AAPL",
                "msg": "Price Spike: +10%",
                "type": "MARKET_SPIKE"
            }
        }
        
        # Process event (Webhooks flush immediately)
        await sentinel.process_event(event)

        # Verify notification was called through HTTP
        assert mock_post.called
        args, kwargs = mock_post.call_args
        payload = kwargs['json']
        assert "AAPL" in payload['content']

@pytest.mark.anyio
async def test_sentinel_vix_logic(mock_sentinel_repo):
    # Setup market service mock
    mock_market = MagicMock()
    # Need > 30 points for Z-Score window
    closes = [20.0] * 30 + [50.0] # 30 stable days + 1 spike
    mock_market.get_ohlcv.return_value = {"close": closes}
    
    with patch('src.services.sentinel_service.SettingsService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('src.services.sentinel_service.CouncilService'):
        
        sentinel = SentinelService(
            market_service=mock_market, 
            user_id="test_user",
            repo=mock_sentinel_repo,
            snapshot_repo=MagicMock()
        )
        triggers = sentinel._check_vix_anomaly()
        
        assert any("VIX Spike" in t['text'] for t in triggers)
