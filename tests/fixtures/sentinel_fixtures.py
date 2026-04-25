import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

@pytest.fixture
def run_async():
    def _run(coro):
        return asyncio.run(coro)
    return _run


@pytest.fixture
def mock_services():
    """Create all mock dependencies via DI (no patching needed).
       Also patches SentinelRepository to prevent DB access during init.
    """
    print("DEBUG: mock_services fixture start")

    market = MagicMock()
    # market_service.get_current_prices is async (awaited in process_tick line 132)
    market.get_current_prices = AsyncMock(return_value={})
    # market_service.get_ohlcv_batch is sync (called without await in _check_position_moves_v2)
    market.get_ohlcv_batch.return_value = {}
    search = MagicMock()
    # search_service.search_financial_context is async (awaited in _analyze_ticker_news)
    search.search_financial_context = AsyncMock(return_value=[])
    transaction = MagicMock()
    council = MagicMock()
    council.start_session = AsyncMock(return_value={"consensus": "Sell slightly"})
    settings = MagicMock()
    settings.user_id = "test_user"
    settings.settings_repo = MagicMock()
    settings.get_setting.side_effect = lambda key, default=None, user_id=None: 0.0 if key == "target_cash_ratio" else default
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo, \
         patch('src.services.sentinel_service.AlchemySnapshotRepository') as MockSnapRepo, \
         patch('src.services.sentinel_service.SentinelService._calibrate_thresholds'), \
         patch('src.services.fred_service.FredService'), \
         patch('src.services.supply_chain_service.SupplyChainService'), \
         patch('src.services.readwise_service.ReadwiseService'), \
         patch('src.agents.factory.AgentFactory', autospec=True) as MockFactory:
 
         # Configure default mock behavior
         mock_repo_instance = MockRepo.return_value
         mock_snap_instance = MockSnapRepo.return_value

         # Configure SentinelAgent mock
         mock_sentinel_agent = MagicMock()
         mock_sentinel_agent.run.return_value = {"priority": "P1", "target_agent": "CIO", "rationale": "Test Risk"}
         MockFactory.create_sentinel_agent.return_value = mock_sentinel_agent



         
         mock_repo_instance.get_all_thresholds.return_value = {
            "vix_high": 25.0,
            "vix_extreme": 40.0,
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
            "fed_funds_change_bps": 25,
            "news_risk_score": 0.6,
         }
         mock_repo_instance.is_duplicate_alert.return_value = False
         mock_snap_instance.get_latest_by_user.return_value = None
         
         yield {
            "market": market,
            "search": search,
            "transaction": transaction,
            "council": council,
            "settings": settings,
            "repo_class": MockRepo,
            "repo_instance": mock_repo_instance,
            "snap_instance": mock_snap_instance
        }

def _create_sentinel(mock_services):
    print("DEBUG: _create_sentinel start")
    from src.services.sentinel_service import SentinelService
    from src.services.risk_keyword_service import RiskKeywordService
    mock_keyword_service = MagicMock(spec=RiskKeywordService)
    mock_keyword_service.get_active_keywords.return_value = []
    mock_keyword_service.contains_risk.return_value = False
    mock_keyword_service.score_text.return_value = (0.0, [])
    print("DEBUG: Instantiating SentinelService")
    res = SentinelService(
        user_id="test_user",
        market_service=mock_services["market"],
        search_service=mock_services["search"],
        transaction_service=mock_services["transaction"],
        council_service=mock_services["council"],
        settings_service=mock_services["settings"],
        keyword_service=mock_keyword_service,
    )
    print("DEBUG: SentinelService instantiated")

    # Mock _redis_buffer so Redis connection failures don't break tests.
    # The buffer stores triggers in memory: add() appends, all_pending() returns them.
    _buffer_store = []

    mock_redis_buffer = MagicMock()

    async def _mock_add(user_id, trigger, wait_mins):
        _buffer_store.append(trigger)
        return True

    async def _mock_all_pending(user_id):
        return list(_buffer_store)

    async def _mock_flush_due(user_id):
        due = list(_buffer_store)
        _buffer_store.clear()
        return due

    mock_redis_buffer.add = _mock_add
    mock_redis_buffer.all_pending = _mock_all_pending
    mock_redis_buffer.flush_due = _mock_flush_due

    res._redis_buffer = mock_redis_buffer

    # res._dispatch_notifications_direct = AsyncMock()

    return res



