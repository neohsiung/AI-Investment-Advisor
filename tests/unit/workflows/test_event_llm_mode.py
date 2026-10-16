"""P3a: event_llm_mode gates every LLM call after the filter; absent event impacts are neutral, never fake."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.workflow_service import EventAnalysisWorkflow

HELD_EVENT = {"ticker": "TSM", "msg": "TSM raises full-year guidance on strong AI demand",
              "url": "https://reuters.com/tsm-guidance"}


def _run(mode, event=HELD_EVENT, holdings=None, raw_setting=None, force_pass=False):
    holdings = holdings if holdings is not None else {"TSM": {"quantity": 10, "avg_price": 160.0}}
    llm = AsyncMock(return_value="### TSM\n**BUY**")
    dist = AsyncMock()
    impact = MagicMock()
    trade = MagicMock()
    with patch("src.services.workflow_service.MarketDataService") as mm, \
         patch("src.services.workflow_service.BaseWorkflow._call_agent_llm", llm), \
         patch("src.services.workflow_service.BaseWorkflow.distribute_report", dist), \
         patch("src.services.workflow_service.TransactionService") as tx, \
         patch("src.services.event_impact_service.EventImpactService", impact), \
         patch("src.services.automated_trading_service.AutomatedTradingService", trade), \
         patch.object(EventAnalysisWorkflow, "_event_budget_exceeded", return_value=""), \
         patch("src.services.settings_service.SettingsService") as ss:
        ss.return_value.get_setting.return_value = raw_setting if raw_setting is not None else mode
        if force_pass:  # relevance filter is not under test here
            fr = MagicMock(should_drop=False, matched_tickers=["TSM"], macro_topic=None, category="company", relevance_score=7.0)
            patcher = patch("src.services.market_news_filter_service.MarketNewsFilterService")
            patcher.start().return_value.evaluate.return_value = fr
        tx.return_value.get_holdings_map.return_value = holdings
        mm.return_value.get_market_context.return_value = {"TSM": {"price_data": {}, "indicators": {}}}
        import asyncio, uuid
        ev = dict(event)
        ev["msg"] = f"{ev['msg']} [{uuid.uuid4().hex[:8]}]"      # defeat the 48h semantic-dedup window
        ev["url"] = f"{ev['url']}/{uuid.uuid4().hex[:8]}"
        res = asyncio.run(EventAnalysisWorkflow("u", "rss", ev).run(dry_run=False))
    if force_pass:
        patcher.stop()
    return res, llm, dist, impact, trade


def test_off_makes_zero_llm_calls_and_writes_nothing():
    res, llm, dist, impact, trade = _run("off")
    assert res.startswith("Skipped") and "event_llm_mode=off" in res
    llm.assert_not_called()
    dist.assert_not_called()
    impact.assert_not_called()        # no hardcoded impact values without an LLM verdict
    trade.assert_not_called()         # no order of any kind from the event path


def test_held_only_skips_unheld_but_analyses_held():
    res, llm, *_ = _run("held_only", holdings={"AAPL": {"quantity": 1}}, force_pass=True)
    assert res.startswith("Skipped") and llm.call_count == 0
    res2, llm2, *_ = _run("held_only", force_pass=True)
    assert not res2.startswith("Skipped") and llm2.call_count >= 2


def test_on_keeps_legacy_behaviour():
    res, llm, *_ = _run("on")
    assert llm.call_count >= 2


def test_unknown_mode_is_treated_as_off():
    res, llm, *_ = _run("banana")
    assert res.startswith("Skipped")
    llm.assert_not_called()


def test_missing_event_impacts_are_neutral_not_faked():
    from src.services.event_impact_service import EventImpactService
    svc = EventImpactService.__new__(EventImpactService)
    svc.user_id = "u"
    svc.repository = MagicMock()
    svc.repository.get_active_impacts.return_value = []
    svc._get_setting = lambda k, d: d
    assert svc.get_ticker_micro_bias("TSM", datetime.now()) == (0.0, [])
    assert svc.get_macro_stress_bias(datetime.now()) == (0.0, 0.0, [])
    # an unreadable impact store is marked, not silently neutral
    svc.repository.get_active_impacts.side_effect = RuntimeError("db down")
    bias, details = svc.get_ticker_micro_bias("TSM", datetime.now())
    assert bias == 0.0 and details and "_fallback_reason" in details[0]
