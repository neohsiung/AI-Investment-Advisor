import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tests.fixtures.sentinel_fixtures import _create_sentinel

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



