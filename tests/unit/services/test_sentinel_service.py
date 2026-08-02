import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService
from src.domain.entities import RiskKeyword

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.get_all_thresholds.return_value = {
        "vix_high": 25.0,
        "vix_extreme": 40.0,
        "vix_spike_sigma": 2.5,
        "position_drop_pct": -5.0,
        "position_spike_pct": 8.0,
        "news_risk_score": 0.6
    }
    return repo

@pytest.fixture
def mock_market_service():
    service = MagicMock()
    service.get_ohlcv.return_value = {"close": [20.0] * 30 + [35.0]} # Simulation for VIX Spike
    service.get_current_prices = AsyncMock(return_value={"AAPL": 150.0})
    service.get_ohlcv_batch.return_value = {"AAPL": {"close": [160.0, 150.0]}} # -6.25% drop
    return service

@pytest.fixture
def mock_tx_service():
    service = MagicMock()
    service.get_user_tickers.return_value = ["AAPL"]
    return service

@pytest.fixture
def mock_settings_service():
    service = MagicMock()
    service.get_setting.return_value = True
    return service

@pytest.fixture
def mock_keyword_service():
    service = MagicMock()
    service.get_active_keywords.return_value = [
        RiskKeyword(id="1", keyword="War", weight=1.0, category="Geopolitical")
    ]
    service.score_text.return_value = (1.0, ["War"])
    return service

@pytest.fixture
def sentinel_service(mock_repo, mock_market_service, mock_tx_service, mock_settings_service, mock_keyword_service):
    mock_buffer = MagicMock()
    mock_buffer.flush_due = AsyncMock(return_value=[])
    mock_buffer.clear = AsyncMock()
    mock_buffer.add_event = AsyncMock()
    # 2026-08-02: process_tick() takes a per-minute Redis lock; always win it
    # here. Dedup behaviour is covered by test_sentinel_tick_lock.py.
    mock_buffer.try_acquire = AsyncMock(return_value=True)
    
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=mock_buffer), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        service = SentinelService(
            user_id="test_user",
            repo=mock_repo,
            market_service=mock_market_service,
            transaction_service=mock_tx_service,
            settings_service=mock_settings_service,
            keyword_service=mock_keyword_service
        )
        return service

def test_check_vix_anomaly(sentinel_service, mock_market_service):
    # Case 1: Spike (35.0 vs average ~20.0)
    triggers = sentinel_service._check_vix_anomaly()
    assert len(triggers) > 0
    assert "VIX Spike" in triggers[0]["text"]

    # Case 2: Normal
    mock_market_service.get_ohlcv.return_value = {"close": [20.0] * 31}
    triggers = sentinel_service._check_vix_anomaly()
    assert len(triggers) == 0

@pytest.mark.asyncio
async def test_check_position_moves_v2(sentinel_service, mock_market_service):
    # AAPL 160 -> 150 is -6.25% drop (threshold -5.0%)
    current_prices = {"AAPL": 150.0}
    triggers = await sentinel_service._check_position_moves_v2(["AAPL"], current_prices)
    assert len(triggers) == 1
    assert "drop_AAPL" in triggers[0]["id"]

@pytest.mark.asyncio
async def test_check_macro_shifts(sentinel_service, mock_market_service):
    mock_market_service.get_macro_data.return_value = {
        "economics": {
            "FedFunds": {"trend": "Up", "value": 5.25, "date": "2024-01-01"},
            "10Y2Y_Spread": {"value": -0.5}
        },
        "market_indicators": {"^VIX": 45.0}
    }
    
    triggers = await sentinel_service._check_macro_shifts()
    texts = [t["text"] for t in triggers]
    assert any("聯邦利率上升" in s for s in texts)
    assert any("殖利率曲線倒掛" in s for s in texts)
    assert any("極端恐慌" in s for s in texts)

@pytest.mark.asyncio
async def test_process_tick(sentinel_service):
    # Mock dimensions to avoid real calls and side effects
    sentinel_service._check_vix_anomaly = MagicMock(return_value=[])
    sentinel_service._check_position_moves_v2 = AsyncMock(return_value=[])
    sentinel_service._check_breaking_news_v2 = AsyncMock(return_value=[])
    sentinel_service._check_macro_shifts = AsyncMock(return_value=[])
    sentinel_service._check_active_sources = AsyncMock(return_value=[])
    sentinel_service._check_global_macro_events = AsyncMock(return_value=[])
    sentinel_service._check_risk_consistency = AsyncMock(return_value=[])
    sentinel_service._handle_cash_deployment_logic = AsyncMock()
    sentinel_service._check_infrastructure_health = AsyncMock(return_value=[])
    sentinel_service._escalate = AsyncMock()
    
    # Tick with no triggers
    await sentinel_service.process_tick()
    sentinel_service._escalate.assert_not_called()

    # Tick with triggers
    sentinel_service._check_vix_anomaly.return_value = [{"text": "VIX Spike", "id": "vix"}]
    await sentinel_service.process_tick()
    sentinel_service._escalate.assert_called_once()

@pytest.mark.asyncio
async def test_call_agent_llm(sentinel_service):
    # Mocking the pipeline
    mock_pipeline = MagicMock()
    mock_pipeline.execute = AsyncMock(return_value=("{\"status\": \"success\", \"data\": \"test\"}", None))
    
    with patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", return_value=mock_pipeline), \
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=MagicMock()):
        
        response = await sentinel_service._call_agent_llm("Thematic", {"test": "data"})
        res_json = json.loads(response)
        assert res_json["status"] == "success"
