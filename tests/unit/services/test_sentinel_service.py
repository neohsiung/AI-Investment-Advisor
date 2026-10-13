import asyncio
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService
from src.domain.entities import RiskKeyword

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.is_duplicate_alert.return_value = False
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
    service.user_id = "test_user"
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
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=MagicMock()), \
         patch("src.services.hard_token_budget_guard_service.HardTokenBudgetGuardService.should_allow_llm", return_value=(True, "allowed")):
        
        response = await sentinel_service._call_agent_llm("Thematic", {"test": "data"})
        res_json = json.loads(response)
        assert res_json["status"] == "success"
        assert res_json["data"] == "test"


@pytest.mark.asyncio
async def test_call_agent_llm_zero_llm_guard_active(sentinel_service):
    """驗證當 0-LLM 守衛生效時，_call_agent_llm 不調用外部模型直接回傳數理規則判定"""
    with patch("src.services.hard_token_budget_guard_service.HardTokenBudgetGuardService.should_allow_llm", return_value=(False, "ZERO_LLM_ENFORCED")):
        response = await sentinel_service._call_agent_llm("Sentinel", {"trigger_source": "price_move"})
        res_json = json.loads(response)
        assert res_json["priority"] == "P2"
        assert res_json["target_agent"] == "CIO"
        assert "0-LLM mathematical rule evaluation" in res_json["rationale"]


@pytest.mark.asyncio
async def test_check_position_exits_atr_and_fixed_stops(sentinel_service):
    """驗證 Tier 0 動態 ATR 初始停損與預設啟用之硬停損防線"""
    # 模擬持倉配置: TSM 買入成本 480，現價 440 (-8.33% 跌幅)
    allocation = {
        "TSM": {
            "shares": 10.0,
            "avg_price": 480.0,
            "current_price": 440.0,
            "weight": 10.0,
        }
    }
    sentinel_service._get_current_allocation = AsyncMock(return_value=allocation)
    sentinel_service.settings_service.get_setting.side_effect = lambda key, default=None, *args: {
        "enable_fixed_stops": True,
        "stop_loss_pct": 8.0,
    }.get(key, default)

    triggers = await sentinel_service._check_position_exits()
    assert len(triggers) >= 1
    assert any("TSM" in t["ticker"] and t["action"] == "trigger_exit" for t in triggers)
    assert any("停損觸發" in t["text"] for t in triggers)


@pytest.mark.asyncio
async def test_call_agent_llm_timeout_handled(sentinel_service):
    """驗證 _call_agent_llm 在遇到逾時時優雅降級並回傳 failed JSON"""
    mock_pipeline = MagicMock()
    mock_pipeline.execute = AsyncMock(side_effect=asyncio.TimeoutError("LLM took too long"))

    with patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", return_value=mock_pipeline), \
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=MagicMock()), \
         patch("src.services.hard_token_budget_guard_service.HardTokenBudgetGuardService.should_allow_llm", return_value=(True, "allowed")):

        response = await sentinel_service._call_agent_llm("Sentinel", {"test": "data"})
        res_json = json.loads(response)
        assert res_json["status"] == "failed"
        assert "timed out" in res_json["error"]


@pytest.mark.asyncio
async def test_do_send_alert_council_timeout_activates_failsafe(sentinel_service):
    """驗證當 Council 研議逾時，_do_send_alert 自動切換至安全模式並記錄警報"""
    sentinel_service.council_service = MagicMock()
    sentinel_service.council_service.start_session = AsyncMock(side_effect=asyncio.TimeoutError("debate hung"))
    sentinel_service.repo.is_duplicate_alert.return_value = False

    triggers = [{
        "text": "🔴 VIX 突增逾時測試",
        "id": "vix_timeout_test",
        "value": 45.0,
        "priority": 1,
        "trigger_type": "risk"
    }]

    mock_broker = MagicMock()
    mock_broker.get_pending_orders = AsyncMock(return_value=[])
    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.event_aggregator.EventAggregator"):
        await sentinel_service._do_send_alert(triggers, source="Sentinel")

    # repo.log_alert should have been called with fail-safe content
    assert sentinel_service.repo.log_alert.called
    logged_topic, logged_text = sentinel_service.repo.log_alert.call_args[0][:2]
    assert "Council Deliberation Timeout" in sentinel_service.repo.log_alert.call_args[1]["metadata"]["decision"]


@pytest.mark.asyncio
async def test_with_timeout_helper():
    """驗證 _with_timeout 輔助函數對協程、逾時與非協程之穩健性"""
    # 正常協程
    async def fast_coro():
        return 42
    res = await SentinelService._with_timeout(fast_coro(), timeout=5.0)
    assert res == 42

    # 逾時協程
    async def slow_coro():
        await asyncio.sleep(0.5)
        return "too slow"
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await SentinelService._with_timeout(slow_coro(), timeout=0.01)

    # 非協程普通值
    res_plain = await SentinelService._with_timeout("sync_string", timeout=1.0)
    assert res_plain == "sync_string"


@pytest.mark.asyncio
async def test_do_send_alert_routine_cash_bypasses_council(sentinel_service):
    """驗證 P3 常規閒置資金警報跳過昂貴的 10-agent Council 研議，並採用階梯建倉說明"""
    sentinel_service.council_service = MagicMock()
    sentinel_service.council_service.start_session = AsyncMock()
    sentinel_service.repo.is_duplicate_alert.return_value = False

    triggers = [{
        "text": "💰 Excess Cash Alert: Actual 63.6% vs Adjusted Target 10.3%",
        "id": "cash_ratio_high_test_user",
        "value": 0.636,
        "priority": 3,
        "trigger_type": "cash_management"
    }]

    mock_broker = MagicMock()
    mock_broker.get_pending_orders = AsyncMock(return_value=[])
    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.event_aggregator.EventAggregator"):
        await sentinel_service._do_send_alert(triggers, source="Sentinel")

    # Council session must NOT be called for routine P3 cash
    assert not sentinel_service.council_service.start_session.called
    assert sentinel_service.repo.log_alert.called
    metadata = sentinel_service.repo.log_alert.call_args[1]["metadata"]
    assert "資金配置監控 (P3)" in metadata["decision"]
    assert "階梯分批建倉" in metadata["decision"]


@pytest.mark.asyncio
async def test_do_send_alert_fallback_critical_suffix_only_for_extreme_or_p1(sentinel_service):
    """驗證安全模式/Fallback 訊息僅在 P1 或極端行情標註 - CRITICAL，P3 不誤標"""
    sentinel_service.council_service = MagicMock()
    sentinel_service.council_service.start_session = AsyncMock(side_effect=asyncio.TimeoutError("timeout"))
    sentinel_service.repo.is_duplicate_alert.return_value = False

    # 1. P3 trigger: should NOT append - CRITICAL
    p3_triggers = [{
        "text": "Normal P3 alert",
        "id": "normal_p3_alert",
        "priority": 3,
        "trigger_type": "generic"
    }]

    mock_broker = MagicMock()
    mock_broker.get_pending_orders = AsyncMock(return_value=[])
    sentinel_service._dispatch_notifications_direct = AsyncMock()

    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.event_aggregator.EventAggregator"):
        await sentinel_service._do_send_alert(p3_triggers, source="Sentinel")
        assert sentinel_service._dispatch_notifications_direct.called
        p3_content = sentinel_service._dispatch_notifications_direct.call_args[1]["content"]
        assert "- CRITICAL" not in p3_content

    # 2. P1 trigger: SHOULD append - CRITICAL in fail-safe fallback
    p1_triggers = [{
        "text": "Extreme P1 alert",
        "id": "extreme_p1_alert",
        "priority": 1,
        "level": "CRITICAL",
        "trigger_type": "risk"
    }]
    sentinel_service._dispatch_notifications_direct.reset_mock()
    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.event_aggregator.EventAggregator"):
        await sentinel_service._do_send_alert(p1_triggers, source="Sentinel")
        assert sentinel_service._dispatch_notifications_direct.called
        p1_content = sentinel_service._dispatch_notifications_direct.call_args[1]["content"]
        assert "- CRITICAL" in p1_content


@pytest.mark.asyncio
async def test_check_risk_consistency_suppresses_cash_when_batch_active(sentinel_service):
    """驗證當分批建倉服務有有效排程批次 (active_batch > 0) 時，動態壓制超額現金警報"""
    mock_snapshot = MagicMock()
    mock_snapshot.to_dict.return_value = {
        "total_nlv": 1687.94,
        "cash_balance": 1072.77,  # 63.6%
        "leverage_ratio": 1.0,
    }
    sentinel_service.snapshot_repo.get_latest_by_user = MagicMock(return_value=mock_snapshot)
    sentinel_service.settings_service.get_setting = MagicMock(return_value=0.10)
    sentinel_service._check_vix_anomaly = MagicMock(return_value=[])

    with patch("src.services.fred_service.FredService") as mock_fred, \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService.get_active_batch_number", new_callable=AsyncMock) as mock_active:
        mock_fred.return_value.get_macro_indicators.return_value = {}
        # Active Batch 2 is staged
        mock_active.return_value = 2

        triggers = await sentinel_service._check_risk_consistency()
        cash_high_triggers = [t for t in triggers if "cash_ratio_high" in t.get("id", "")]
        assert len(cash_high_triggers) == 0


@pytest.mark.asyncio
async def test_check_risk_consistency_emits_cash_when_batch_not_active(sentinel_service):
    """驗證當分批建倉無排程批次 (active_batch == 0) 時，正常發出超額現金警報"""
    mock_snapshot = MagicMock()
    mock_snapshot.to_dict.return_value = {
        "total_nlv": 1687.94,
        "cash_balance": 1072.77,  # 63.6%
        "leverage_ratio": 1.0,
    }
    sentinel_service.snapshot_repo.get_latest_by_user = MagicMock(return_value=mock_snapshot)
    sentinel_service.settings_service.get_setting = MagicMock(return_value=0.10)
    sentinel_service._check_vix_anomaly = MagicMock(return_value=[])

    with patch("src.services.fred_service.FredService") as mock_fred, \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService.get_active_batch_number", new_callable=AsyncMock) as mock_active:
        mock_fred.return_value.get_macro_indicators.return_value = {}
        # No active batch staged
        mock_active.return_value = 0

        triggers = await sentinel_service._check_risk_consistency()
        cash_high_triggers = [t for t in triggers if "cash_ratio_high" in t.get("id", "")]
        assert len(cash_high_triggers) == 1
        assert "Actual 63.6%" in cash_high_triggers[0]["text"]

