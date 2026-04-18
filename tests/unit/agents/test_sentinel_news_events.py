import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tests.fixtures.sentinel_fixtures import _create_sentinel

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

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                triggers = await sentinel._check_breaking_news_v2(["AAPL"])

            assert len(triggers) == 1
            assert "AAPL" in triggers[0]["id"]
            assert "新聞異動" in triggers[0]["text"]
            assert "加權分數" in triggers[0]["text"]
            # Verify hits were recorded via keyword_service
            assert sentinel.keyword_service.record_hit.call_count >= 1

        run_async(_test())

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

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                triggers = await sentinel._check_breaking_news_v2(["MSFT"])

            assert len(triggers) == 0

        run_async(_test())

    def test_tavily_failure_graceful(self, mock_services, run_async):
        """Tavily API fails — returns empty, no crash."""
        sentinel = _create_sentinel(mock_services)
        mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
        mock_services["market"].get_news.return_value = None
        mock_services["search"].search_financial_context.side_effect = Exception("Tavily down")

        keywords = self._get_test_keywords()
        sentinel.keyword_service.get_active_keywords.return_value = keywords

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                triggers = await sentinel._check_breaking_news_v2(["AAPL"])

            assert len(triggers) == 0

        run_async(_test())



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
        expected_hash = f"rss_{hashlib.sha256(url.encode()).hexdigest()}"
        assert normalized["signal_id"] == expected_hash
        assert normalized["url"] == url



