"""
Tests for SentinelService Multi-Dimensional Triggers (v3.5)
測試哨兵服務多維觸發機制

Coverage targets:
  - VIX adaptive & static triggers
  - Position price moves (drop / spike)
  - Breaking news risk detection (Tavily)
  - Macro shifts (FRED)
  - Escalation → Council + LINE
  - Error handling per dimension
"""
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
    market = MagicMock()
    search = MagicMock()
    transaction = MagicMock()
    council = MagicMock()
    council.start_session = AsyncMock(return_value={"consensus": "Sell slightly"})
    settings = MagicMock()
     # Patch the repository class so SentinelService() allows mocking init
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as MockRepo:
         # Configure default mock behavior if needed
         mock_repo_instance = MockRepo.return_value
         mock_repo_instance.get_all_thresholds.return_value = {
            "vix_high": 25.0,
            "vix_extreme": 40.0,
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
            "fed_funds_change_bps": 25,
            "news_risk_score": 0.6,
         }
         mock_repo_instance.is_duplicate_alert.return_value = False
         
         yield {
            "market": market,
            "search": search,
            "transaction": transaction,
            "council": council,
            "settings": settings,
            "repo_class": MockRepo,
            "repo_instance": mock_repo_instance
        }

def _create_sentinel(mock_services):
    from src.services.sentinel_service import SentinelService
    from src.services.risk_keyword_service import RiskKeywordService
    mock_keyword_service = MagicMock(spec=RiskKeywordService)
    mock_keyword_service.get_active_keywords.return_value = []
    mock_keyword_service.contains_risk.return_value = False
    mock_keyword_service.score_text.return_value = (0.0, [])
    return SentinelService(
        market_service=mock_services["market"],
        search_service=mock_services["search"],
        transaction_service=mock_services["transaction"],
        council_service=mock_services["council"],
        settings_service=mock_services["settings"],
        keyword_service=mock_keyword_service,
    )


# ──────────────────────────────────────────
# Dimension 1: VIX
# ──────────────────────────────────────────

class TestVIXAnomaly:
    def test_calm_market_no_trigger(self, mock_services, run_async):
        """VIX stable at 15 — no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv.return_value = {"close": [15.0] * 60}
        mock_services["transaction"].get_user_tickers.return_value = []

        async def _test():
            # Patch _get_all_user_ids and _check_active_sources to avoid DB
            with patch.object(sentinel, '_get_all_user_ids', return_value=[]), \
                 patch.object(sentinel, '_check_active_sources', return_value=[]), \
                 patch('httpx.AsyncClient.post') as mock_post:
                await sentinel.process_tick()
                mock_post.assert_not_called()
            mock_services["council"].start_session.assert_not_called()

        run_async(_test())

    def test_vix_spike_triggers_council(self, mock_services, run_async):
        """VIX spikes from 15 to 25 — adaptive trigger fires."""
        sentinel = _create_sentinel(mock_services)
        history = [15.0] * 59 + [25.0]
        mock_services["market"].get_ohlcv.return_value = {"close": history}
        mock_services["market"].get_current_prices.return_value = {}
        mock_services["market"].get_macro_data.return_value = {}
        mock_services["transaction"].get_user_tickers.return_value = []

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=[]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "VIX Spike" in args[0]

        run_async(_test())

    def test_vix_static_fallback(self, mock_services, run_async):
        """Short history — uses static threshold."""
        sentinel = _create_sentinel(mock_services)
        # 3.9 - Ensure thresholds are mockable
        sentinel.thresholds = {"vix_high": 20.0}
        
        mock_services["market"].get_ohlcv.return_value = {"close": [22.0]}
        
        async def _test():
            # Test the dimension logic directly to ensure it works
            triggers = sentinel._check_vix_anomaly()
            assert len(triggers) == 1
            assert "vix_high_static" in triggers[0]["id"]
            
            # Now test the escalation via _escalate
            with patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
                await sentinel._escalate(triggers)
                await sentinel._flush_buffer(force=True) # Force flush for testing
                mock_services["council"].start_session.assert_called_once()
                assert mock_post.called

        run_async(_test())


# ──────────────────────────────────────────
# Dimension 2: Position Price Moves
# ──────────────────────────────────────────

class TestPositionMoves:
    def test_position_drop_trigger(self, mock_services, run_async):
        """Stock drops > 5% intraday — triggers alert."""
        # Use the global mock instance from the fixture
        repo_instance = mock_services["repo_instance"]
        repo_instance.get_all_thresholds.return_value = {
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
        }

        async def _test():
            # Create sentinel - it will use the mocked Repo class from fixture
            sentinel = _create_sentinel(mock_services)
            
            # Setup market data for the drop
            mock_services["market"].get_ohlcv_batch.return_value = {
                "AAPL": {"close": [100.0, 89.0]} # -11%
            }
            mock_services["market"].get_current_prices.return_value = {"AAPL": 89.0}
            mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
            
            # Mock internal user methods
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                    await sentinel.process_tick()
                    await sentinel._flush_buffer(force=True)

            # Verification
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "AAPL" in args[0]

        run_async(_test())

    def test_position_spike_trigger(self, mock_services, run_async):
        """Stock spikes > 8% intraday — triggers alert."""
        # Use the global mock instance
        repo_instance = mock_services["repo_instance"]
        repo_instance.get_all_thresholds.return_value = {
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
        }
    
        async def _test():
            sentinel = _create_sentinel(mock_services)
            
            # Market data for spike
            mock_services["market"].get_ohlcv_batch.return_value = {
                "TSLA": {"close": [100.0, 110.0]} # +10%
            }
            mock_services["market"].get_current_prices.return_value = {"TSLA": 110.0}
            mock_services["transaction"].get_user_tickers.return_value = ["TSLA"]
            
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)

            # Verification
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "TSLA" in args[0]

        run_async(_test())

    def test_position_bubble_trigger(self, mock_services, run_async):
        """Stock rises > 8% — triggers bubble warning."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv_batch.return_value = {
            "TSLA": {"close": [100.0, 110.0]}
        }
        mock_services["market"].get_current_prices.return_value = {"TSLA": 110.0}
        mock_services["market"].get_macro_data.return_value = {}
        mock_services["transaction"].get_user_tickers.return_value = ["TSLA"]

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "TSLA" in args[0]
            assert "漲" in args[0]

        run_async(_test())

    def test_no_trigger_small_move(self, mock_services, run_async):
        """Stock moves < 5% — no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv_batch.return_value = {
            "MSFT": {"close": [100.0, 98.0]}
        }
        mock_services["market"].get_current_prices.return_value = {"MSFT": 98.0}
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]), \
                 patch.object(sentinel, '_check_active_sources', return_value=[]):
                await sentinel.process_tick()
            mock_services["council"].start_session.assert_not_called()

        run_async(_test())


# ──────────────────────────────────────────
# Dimension 3: Breaking News (Tavily)
# ──────────────────────────────────────────

class TestBreakingNews:
    def _get_test_keywords(self):
        """Helper to create test keywords."""
        from src.domain.entities import RiskKeyword, RiskCategory
        return [
            RiskKeyword(id="k1", keyword="sec investigation", weight=0.9, category=RiskCategory.LEGAL),
            RiskKeyword(id="k2", keyword="fraud", weight=0.9, category=RiskCategory.LEGAL),
            RiskKeyword(id="k3", keyword="earnings", weight=0.1, category=RiskCategory.FINANCIAL),
        ]

    def test_risk_keyword_weighted_trigger(self, mock_services, run_async):
        """Tavily returns SEC + fraud news — weighted score >= 0.6 triggers."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
        mock_services["market"].get_news.return_value = [
            {"title": "AAPL faces SEC investigation for fraud", "summary": "SEC investigation ongoing"}
        ]

        keywords = self._get_test_keywords()
        sentinel.keyword_service.get_active_keywords.return_value = keywords

        with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news_v2(["AAPL"])

        assert len(triggers) == 1
        assert "AAPL" in triggers[0]["id"]
        assert "新聞異動" in triggers[0]["text"]
        assert "加權分數" in triggers[0]["text"]
        # Verify hits were recorded via keyword_service
        assert sentinel.keyword_service.record_hit.call_count >= 1

    def test_no_risk_keyword_no_trigger(self, mock_services, run_async):
        """Tavily returns normal news — weighted score < 0.6, no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]
        mock_services["market"].get_news.return_value = [
            {"title": "MSFT reports strong Q4 earnings", "summary": "Revenue up 15%"}
        ]

        # "earnings" has weight 0.1, below threshold
        keywords = self._get_test_keywords()
        sentinel.keyword_service.get_active_keywords.return_value = keywords

        with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news_v2(["MSFT"])

        assert len(triggers) == 0

    def test_tavily_failure_graceful(self, mock_services, run_async):
        """Tavily API fails — returns empty, no crash."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
        mock_services["market"].get_news.return_value = None
        mock_services["search"].search_financial_context.side_effect = Exception("Tavily down")

        keywords = self._get_test_keywords()
        sentinel.keyword_service.get_active_keywords.return_value = keywords

        with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news_v2(["AAPL"])

        assert len(triggers) == 0


# ──────────────────────────────────────────
# Dimension 4: Macro Shifts (FRED)
# ──────────────────────────────────────────

class TestMacroShifts:
    def test_fed_rate_up_triggers(self, mock_services):
        """Fed funds rate trending up — triggers alert."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.5, "trend": "Up", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": 0.5},
            }
        }

        triggers = sentinel._check_macro_shifts()
        assert len(triggers) == 1
        assert "聯邦利率上升" in triggers[0]["text"]

    def test_yield_inversion_triggers(self, mock_services):
        """Yield curve inverted — triggers alert."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.0, "trend": "Down", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": -0.3},
            }
        }

        triggers = sentinel._check_macro_shifts()
        assert len(triggers) == 1
        assert "殖利率曲線倒掛" in triggers[0]["text"]

    def test_normal_macro_no_trigger(self, mock_services):
        """Normal macro conditions — no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.0, "trend": "Down", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": 0.5},
            }
        }

        triggers = sentinel._check_macro_shifts()
        assert len(triggers) == 0


# ──────────────────────────────────────────
# Escalation
# ──────────────────────────────────────────

class TestEscalation:
    def test_escalation_calls_council_and_line(self, mock_services, run_async):
        """Triggers escalate to Council then Notification API."""
        sentinel = _create_sentinel(mock_services)
        sentinel.settings_service.user_id = "U123"
        sentinel.user_id = "U123"

        async def _test():
            with patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
                await sentinel._escalate([{"text": "Test trigger 1", "id": "t1"}, {"text": "Test trigger 2", "id": "t2"}])
                await sentinel._flush_buffer(force=True)
    
                mock_services["council"].start_session.assert_called_once()
                assert mock_post.called
                
                # Check payload
                call_args = mock_post.call_args
                payload = call_args.kwargs['json']
                assert payload["user_id"] == "U123"
                assert "偵測到以下重要訊號 (2)" in payload["content"]

        run_async(_test())


# ──────────────────────────────────────────
# Error Handling
# ──────────────────────────────────────────

class TestErrorHandling:
    def test_full_tick_error_no_crash(self, mock_services, run_async, caplog):
        """Dimension-level failure is caught — tick doesn't crash."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv.side_effect = Exception("API Down")

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=[]):
                await sentinel.process_tick()
            # Per-dimension error isolation: logged at dimension level
            assert "VIX check failed" in caplog.text

        run_async(_test())

# ──────────────────────────────────────────
# Data Source Polling & Thematic Updates
# ──────────────────────────────────────────

class TestSourcePollingAndThematic:
    def test_poll_alternative_me(self, mock_services, run_async):
        """Test Fear & Greed API polling"""
        sentinel = _create_sentinel(mock_services)
        with patch('requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": [{"value": "15", "value_classification": "Extreme Fear"}]}
            mock_get.return_value = mock_resp
            
            async def _test():
                res = await sentinel._poll_single_source("alternative_me", {})
                assert res is not None
                assert res["id"] == "fng_extreme"
                assert res["value"] == 15
            run_async(_test())

    def test_poll_tiingo(self, mock_services, run_async):
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].tiingo.get_news.return_value = [{"title": "AAPL crash amid SEC investigation"}]
        with patch.object(sentinel, '_get_polling_tickers', return_value=["AAPL"]), \
             patch.object(sentinel, '_contains_risk_keywords', return_value=True):
            async def _test():
                res = await sentinel._poll_single_source("tiingo", {})
                assert res is not None
                assert isinstance(res, list)
                assert len(res) >= 1
                assert "tiingo_risk" in res[0]["id"]
            run_async(_test())

    def test_poll_finnhub(self, mock_services, run_async):
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].finnhub.get_sentiment.return_value = {"sentiment": -0.7}
        with patch.object(sentinel, '_get_polling_tickers', return_value=["AAPL"]):
            async def _test():
                res = await sentinel._poll_single_source("finnhub", {})
                assert res is not None
                assert isinstance(res, list)
                assert len(res) >= 1
                assert "finnhub_neg" in res[0]["id"]
            run_async(_test())

    def test_poll_alpha_vantage(self, mock_services, run_async):
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].alpha_vantage.get_news.return_value = [{"sentiment_label": "Bearish", "title": "Market crash fears rise"}]
        with patch.object(sentinel, '_get_polling_tickers', return_value=["AAPL"]):
            async def _test():
                res = await sentinel._poll_single_source("alpha_vantage", {})
                assert res is not None
                assert isinstance(res, list)
                assert len(res) >= 1
                assert "av_risk" in res[0]["id"]
            run_async(_test())
        
    def test_poll_readwise(self, mock_services, run_async):
        sentinel = _create_sentinel(mock_services)
        sentinel.settings_service.get_setting.return_value = "2024-01-01"
        
        with patch('src.services.readwise_service.ReadwiseService') as MockRW:
            rw_instance = MockRW.return_value
            rw_instance.fetch_and_analyze_highlights.return_value = [
                {
                    "id": "123",
                    "text": "Important highlight about TSLA",
                    "analysis": {
                        "requires_action": True,
                        "reasoning": "TSLA strategy",
                        "suggested_action": "Buy TSLA"
                    }
                }
            ]
            async def _test():
                res = await sentinel._poll_single_source("readwise", {})
                assert res is not None
                assert len(res) == 1
                assert res[0]["id"] == "readwise_123"
                assert res[0]["category"] == "READWISE_INSIGHT"
            run_async(_test())

    def test_trigger_thematic_update(self, mock_services, run_async):
        """Test asynchronous thematic update trigger"""
        # Test asynchronous thematic update trigger
        # 測試非同步題材更新觸發
        sentinel = _create_sentinel(mock_services)
        with patch('src.agents.factory.AgentFactory.create_thematic_agent', create=True) as mock_create, \
             patch('asyncio.get_event_loop') as mock_get_loop:
            
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.is_closed.return_value = False
            
            # Mock analyze for thematic agent
            mock_agent_instance = MagicMock()
            mock_create.return_value = mock_agent_instance
            
            # Call synchronous wrapper that fires task
            sentinel._trigger_thematic_update("Nvidia releases new chip", "ai", ["AAPL"])
            
            assert mock_loop.run_in_executor.called

    def test_check_active_sources(self, mock_services, run_async):
        sentinel = _create_sentinel(mock_services)
        sentinel.settings_service.get_setting.return_value = "true"
        async def _test():
            res = await sentinel._check_active_sources()
            assert isinstance(res, list)
        run_async(_test())
        
    def test_analyze_ticker_news_ai_energy(self, mock_services):
        sentinel = _create_sentinel(mock_services)
        
        # Force empty settings so bootstrapping triggers
        sentinel.settings_service.get_setting.return_value = None
        
        mock_results = [{
            "title": "Microsoft signs PPA for datacenter power",
            "snippet": "nuclear"
        }]
        
        kw = MagicMock(keyword="ppa")
        kw.score.return_value = 0.8
        mock_keywords = [kw]
        
        mock_services["market"].get_news.return_value = []
        mock_services["search"].search_financial_context.return_value = mock_results
        
        score, summary = sentinel._analyze_ticker_news("MSFT", mock_keywords)
        # PPA deals get score boost
        assert score > 0.0

    def test_analyze_ticker_news_physical_ai(self, mock_services):
        sentinel = _create_sentinel(mock_services)
        sentinel.settings_service.get_setting.side_effect = lambda k: "TSLA" if "physical_ai" in k else None
        
        mock_results = [{
            "title": "TSLA Robotaxi",
            "snippet": "autonomous driving"
        }]
        kw = MagicMock(keyword="robotaxi")
        kw.score.return_value = 0.9
        mock_keywords = [kw]
        
        mock_services["market"].get_news.return_value = []
        mock_services["search"].search_financial_context.return_value = mock_results
        
        score, summary = sentinel._analyze_ticker_news("TSLA", mock_keywords)
        # Should detect Physical AI keywords and boost
        assert score > 0.0


class TestEventDriven:
    def test_process_event_general(self, mock_services, run_async):
        """Test general event processing"""
        # Test general event processing
        # 測試一般事件處理
        sentinel = _create_sentinel(mock_services)
        event = {"source": "test_source", "data": {"msg": "Test Message", "ticker": "AAPL"}}
        
        async def _test():
            with patch.object(sentinel, '_escalate', new_callable=AsyncMock) as mock_escalate:
                await sentinel.process_event(event)
                assert mock_escalate.called
        run_async(_test())

    def test_process_event_earnings_premium(self, mock_services, run_async):
        """Test earnings call event with shortage premium"""
        # Test earnings call event with shortage premium
        # 測試帶有供應短缺溢價的財報電話事件
        sentinel = _create_sentinel(mock_services)
        event = {"source": "earnings_call", "data": {"msg": "Earnings Report", "ticker": "TSMC"}}
        
        async def _test():
            with patch('src.services.supply_chain_service.SupplyChainService.get_shortage_premium', 
                       return_value={"has_premium": True, "narrative": "Severe shortage"}) as mock_sc, \
                 patch.object(sentinel, '_escalate', new_callable=AsyncMock) as mock_escalate:
                await sentinel.process_event(event)
                assert mock_escalate.called
        run_async(_test())

    def test_realtime_vix_spike(self, mock_services, run_async):
        """Test real-time VIX alert logic"""
        # Test real-time VIX alert logic
        # 測試即時 VIX 警報邏輯
        sentinel = _create_sentinel(mock_services)
        event = {"ev": "A", "sym": "VIX", "c": 35.0} # VIX > 25
        
        async def _test():
            with patch.object(sentinel, '_escalate', new_callable=AsyncMock) as mock_escalate:
                await sentinel.on_realtime_event(event)
                assert mock_escalate.called
        run_async(_test())


class TestRssDeduplication:
    def test_process_event_with_provided_signal_id(self, mock_services, run_async):
        """Verify that process_event uses the signal_id from the payload."""
        sentinel = _create_sentinel(mock_services)
        event = {
            "source": "n8n",
            "data": {
                "msg": "Test RSS Item",
                "ticker": "GLOBAL",
                "signal_id": "rss_abc123"
            }
        }
        
        async def _test():
            with patch.object(sentinel, '_escalate', new_callable=AsyncMock) as mock_escalate:
                await sentinel.process_event(event)
                # Check that _escalate was called with the correct signal_id
                args = mock_escalate.call_args[0]
                assert args[0][0]["id"] == "rss_abc123"
        run_async(_test())

    def test_suppression_logic_with_signal_id(self, mock_services, run_async):
        """Verify that _do_send_alert suppresses duplicate signal_ids."""
        sentinel = _create_sentinel(mock_services)
        mock_services["repo_instance"].is_duplicate_alert.return_value = True
        
        triggers = [{"text": "Duplicate Signal", "id": "rss_abc123"}]
        
        async def _test():
            with patch.object(sentinel, 'council_service') as mock_council:
                await sentinel._do_send_alert(triggers)
                # Council should NOT be consulted because the signal is a duplicate
                mock_council.start_session.assert_not_called()
        run_async(_test())

    def test_n8n_parser_generates_correct_signal_id(self):
        """Verify N8nParser hash-based signal_id generation."""
        from src.services.webhook_service import N8nParser
        import hashlib
        
        url = "https://example.com/news/1"
        payload = {
            "body": {
                "link": url,
                "message": "Breaking News"
            }
        }
        
        normalized = N8nParser.parse(payload)
        expected_hash = f"rss_{hashlib.md5(url.encode()).hexdigest()}"
        assert normalized["signal_id"] == expected_hash
        assert normalized["url"] == url

