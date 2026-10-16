"""Finnhub polling: gating, dedupe, per-run cap, no silent 'no news' on missing key."""
import asyncio
from unittest.mock import MagicMock, patch

from src.services.finnhub_poll_service import FinnhubPollService


class _Settings:
    def __init__(self, **kv):
        self.kv = kv

    def get_setting(self, key, default=None, user_id=None):
        return self.kv.get(key, default)


class _Redis:
    def __init__(self):
        self.s = set()

    def exists(self, k):
        return k in self.s

    def set(self, k, v, ex=None, nx=False):
        self.s.add(k)
        return True


def _svc(enabled=True, key="k", items=None, cap=3):
    prov = MagicMock(api_key=key)
    prov.fetch_news.return_value = items if items is not None else [
        {"title": f"h{i}", "url": f"http://x/{i}"} for i in range(5)]
    wh = MagicMock(_redis=_Redis())
    wh._is_duplicate.return_value = False
    wh._acquire_concurrency_lock.return_value = True
    repo = MagicMock()
    repo.get_all.return_value = [{"ticker": "AAPL"}]
    return FinnhubPollService("u", provider=prov, webhook=wh,
                              settings=_Settings(finnhub_poll_enabled=enabled, finnhub_poll_max_events=cap), repo=repo)


def _run(svc):
    wf = MagicMock()
    wf.return_value.run = MagicMock(side_effect=lambda: asyncio.sleep(0))
    with patch("src.services.workflow_service.EventAnalysisWorkflow", wf):
        return asyncio.run(svc.run()), wf


def test_disabled_is_noop():
    res, wf = _run(_svc(enabled=False))
    assert res["status"] == "disabled" and not wf.called


def test_missing_key_reports_error():
    res, wf = _run(_svc(key=None))
    assert res == {"status": "error", "reason": "missing_api_key"} and not wf.called


def test_cap_defers_and_second_poll_skips_seen():
    svc = _svc(cap=2)
    res, wf = _run(svc)
    assert res["dispatched"] == 2 and res["deferred"] == 3 and wf.call_count == 2
    res2, _ = _run(svc)  # first two are marked seen; remaining 3 are new, capped at 2
    assert res2["new"] == 3 and res2["dispatched"] == 2


def test_redis_fault_treated_as_seen():
    svc = _svc()
    svc.webhook._redis = MagicMock(exists=MagicMock(side_effect=RuntimeError("down")))
    res, wf = _run(svc)
    assert res["new"] == 0 and not wf.called


def test_event_budget_gate_caps_and_doubles_for_held():
    from src.services.workflow_service import EventAnalysisWorkflow

    class R:
        def __init__(self): self.c = {}
        def incr(self, k): self.c[k] = self.c.get(k, 0) + 1; return self.c[k]
        def expire(self, k, t): pass

    r = R()
    wf = EventAnalysisWorkflow.__new__(EventAnalysisWorkflow)
    wf.user_id = "u"; wf.logger = MagicMock()
    with patch("src.services.settings_service.SettingsService") as SS, \
         patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=r):
        SS.return_value.get_setting.return_value = 2
        assert wf._event_budget_exceeded(False) == ""
        assert wf._event_budget_exceeded(False) == ""
        assert "budget" in wf._event_budget_exceeded(False)      # 3rd non-held over cap 2
        assert wf._event_budget_exceeded(True) == ""             # held has its own, doubled counter
        SS.return_value.get_setting.return_value = 0
        assert wf._event_budget_exceeded(False) == ""            # 0 = unlimited
