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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
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
    return SentinelService(
        market_service=mock_services["market"],
        search_service=mock_services["search"],
        transaction_service=mock_services["transaction"],
        council_service=mock_services["council"],
        settings_service=mock_services["settings"],
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
            mock_services["market"].get_ohlcv.side_effect = lambda ticker, days=30: {
                "close": [15.0] * 60 if ticker == "^VIX" else [100.0, 89.0] # 89 is -11% from 100
            }
            mock_services["market"].get_current_prices.return_value = {"AAPL": 89.0}
            mock_services["market"].get_macro_data.return_value = {}
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
            mock_services["market"].get_ohlcv.side_effect = lambda ticker, days=30: {
                "close": [15.0] * 60 if ticker == "^VIX" else [100.0, 110.0] # +10%
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
        mock_services["market"].get_ohlcv.side_effect = lambda ticker, days=30: {
            "close": [15.0] * 60 if ticker == "^VIX" else [100.0, 110.0]
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
        mock_services["market"].get_ohlcv.side_effect = lambda ticker, days=30: {
            "close": [15.0] * 60 if ticker == "^VIX" else [100.0, 98.0]
        }
        mock_services["market"].get_current_prices.return_value = {"MSFT": 98.0}
        mock_services["market"].get_macro_data.return_value = {}
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
    def _mock_repo(self, mock_services, keywords=None):
        """Helper to patch RiskKeywordRepository with test keywords."""
        from src.domain.entities import RiskKeyword, RiskCategory
        if keywords is None:
            keywords = [
                RiskKeyword(id="k1", keyword="sec investigation", weight=0.9, category=RiskCategory.LEGAL),
                RiskKeyword(id="k2", keyword="fraud", weight=0.9, category=RiskCategory.LEGAL),
                RiskKeyword(id="k3", keyword="earnings", weight=0.1, category=RiskCategory.FINANCIAL),
            ]
        return keywords

    def test_risk_keyword_weighted_trigger(self, mock_services, run_async):
        """Tavily returns SEC + fraud news — weighted score >= 0.6 triggers."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
        mock_services["search"].search_financial_context.return_value = [
            {"title": "AAPL faces SEC investigation for fraud", "snippet": "SEC investigation ongoing"}
        ]

        keywords = self._mock_repo(mock_services)
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = keywords
        mock_repo.record_hit = MagicMock()

        with patch('src.services.sentinel_service.AlchemyRiskKeywordRepository', return_value=mock_repo), \
             patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news()

        assert len(triggers) == 1
        assert "AAPL" in triggers[0]["id"]
        assert "新聞異動" in triggers[0]["text"]
        assert "加權分數" in triggers[0]["text"]
        # Verify hits were recorded
        assert mock_repo.record_hit.call_count >= 1

    def test_no_risk_keyword_no_trigger(self, mock_services, run_async):
        """Tavily returns normal news — weighted score < 0.6, no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]
        mock_services["search"].search_financial_context.return_value = [
            {"title": "MSFT reports strong Q4 earnings", "snippet": "Revenue up 15%"}
        ]

        # "earnings" has weight 0.1, below threshold
        keywords = self._mock_repo(mock_services)
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = keywords

        with patch('src.services.sentinel_service.AlchemyRiskKeywordRepository', return_value=mock_repo), \
             patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news()

        assert len(triggers) == 0

    def test_tavily_failure_graceful(self, mock_services, run_async):
        """Tavily API fails — returns empty, no crash."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
        mock_services["search"].search_financial_context.side_effect = Exception("Tavily down")

        mock_repo = MagicMock()
        mock_repo.get_all.return_value = self._mock_repo(mock_services)

        with patch('src.services.sentinel_service.AlchemyRiskKeywordRepository', return_value=mock_repo), \
             patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
            triggers = sentinel._check_breaking_news()

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

        async def _test():
            with patch.dict('os.environ', {"LINE_USER_ID": "U123"}), \
                 patch('httpx.AsyncClient.post', return_value=MagicMock(status_code=202)) as mock_post:
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
