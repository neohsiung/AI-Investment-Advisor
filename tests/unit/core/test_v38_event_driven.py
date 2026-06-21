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
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo, \
         patch('src.services.sentinel_service.SentinelService._calibrate_thresholds'):

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
         patch('src.services.fred_service.FredService'), \
         patch('src.services.supply_chain_service.SupplyChainService'), \
         patch('src.services.readwise_service.ReadwiseService'), \
         patch('src.agents.factory.AgentFactory', autospec=True) as MockFactory:
        
        # Configure SentinelAgent mock
        mock_sentinel_agent = MagicMock()
        mock_sentinel_agent.run.return_value = {"priority": "P1", "target_agent": "CIO", "rationale": "High drop"}
        MockFactory.create_sentinel_agent.return_value = mock_sentinel_agent

        sentinel = SentinelService(
            council_service=mock_council,
            user_id="test_user",
            repo=mock_sentinel_repo,
            snapshot_repo=MagicMock() # Mock snapshot repo too
        )
        sentinel.current_vix = 40.0
        sentinel.settings_service.user_id = "test_user"
        # Suppress cash alert
        sentinel.settings_service.get_setting.side_effect = lambda key, default=None, user_id=None: 0.0 if key == "target_cash_ratio" else default
        # Mock direct dispatch
        sentinel._dispatch_notifications_direct = AsyncMock()

        # Mock _redis_buffer so Redis connection failures don't break tests
        _buffer_store = []
        mock_redis_buffer = MagicMock()
        async def _mock_add(uid, t, w): _buffer_store.append(t); return True
        async def _mock_all_pending(uid): return list(_buffer_store)
        async def _mock_flush_due(uid): due = list(_buffer_store); _buffer_store.clear(); return due
        mock_redis_buffer.add = _mock_add
        mock_redis_buffer.all_pending = _mock_all_pending
        mock_redis_buffer.flush_due = _mock_flush_due
        sentinel._redis_buffer = mock_redis_buffer

        # Simulate an event
        event = {
            "source": "mktrecap",
            "data": {
                "ticker": "AAPL",
                "msg": "Price Spike: +10%",
                "type": "MARKET_SPIKE"
            }
        }
        
        # Process event (Webhooks flush immediately in theory, but here we force it)
        await sentinel.process_event(event)
        await sentinel._flush_buffer(force=True)


        # Verify notification was called directly
        assert sentinel._dispatch_notifications_direct.called
        args, kwargs = sentinel._dispatch_notifications_direct.call_args
        assert "AAPL" in kwargs['content']

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
