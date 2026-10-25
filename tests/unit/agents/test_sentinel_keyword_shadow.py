"""Sentinel records the shadow keyword rule beside the live one without changing the live decision.
哨兵在正式規則旁記錄 shadow 規則的結果，不改變正式判斷。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities import RiskKeyword
from src.services import keyword_shadow_recorder
from tests.fixtures.sentinel_fixtures import _create_sentinel


def _keywords():
    return [RiskKeyword(id="k-es", keyword="es", weight=1.0, source="trends")]


def _sentinel(mock_services):
    s = _create_sentinel(mock_services)
    s.settings_service.get_setting.return_value = ["CEG"]   # skip theme bootstrapping
    mock_services["market"].get_news.return_value = [{"title": "ES futures slide overnight", "summary": ""}]
    return s


def test_ticker_news_records_live_hit_and_shadow_miss(mock_services, run_async):
    s = _sentinel(mock_services)
    with patch.object(keyword_shadow_recorder, "record") as record:
        score, _ = run_async(s._analyze_ticker_news("SPY", _keywords()))
    assert score == 1.0                                    # live decision unchanged
    record.assert_called_once_with("ticker_news", True, False, "SPY")
    assert s.keyword_service.record_hit.call_count == 1    # shadow never records hits


def test_ticker_news_live_score_survives_a_redis_failure(mock_services, run_async):
    s = _sentinel(mock_services)
    with patch.object(keyword_shadow_recorder, "get_redis_sync", side_effect=ConnectionError("down")):
        score, _ = run_async(s._analyze_ticker_news("SPY", _keywords()))
    assert score == 1.0


@pytest.mark.asyncio
async def test_global_event_records_each_candidate():
    from src.services.sentinel_service import SentinelService

    svc = SentinelService.__new__(SentinelService)
    svc.thresholds = {"news_risk_score": 0.6}
    svc.settings_service = MagicMock()
    svc.settings_service.get_setting.side_effect = lambda k, d=None: d
    svc.keyword_service = MagicMock()
    svc.keyword_service.score_text.return_value = (1.0, ["es"])
    svc.keyword_service.shadow_score_text.return_value = 0.0
    svc.search_service = MagicMock()
    svc.search_service.search_financial_context = AsyncMock(return_value=[
        {"title": "Morgan Stanley Names It Top Pick", "link": "https://www.reuters.com/a", "snippet": ""},
    ])
    svc._acquire_cooldown = AsyncMock(return_value=True)
    with patch.object(keyword_shadow_recorder, "record") as record:
        await svc._check_global_macro_events()
    assert record.call_count == 2   # two queries, one candidate each
    path, live, shadow, _ = record.call_args.args
    assert (path, live, shadow) == ("global_event", True, False)
