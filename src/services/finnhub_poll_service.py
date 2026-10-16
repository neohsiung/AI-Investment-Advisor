"""Finnhub news polling — replaces the public webhook ingress (no inbound exposure needed).
Finnhub 新聞輪詢——取代公網 webhook 入口（不需任何入站暴露）。

Polls company news for active universe tickers, reuses WebhookService dedupe, and hands new items
to the same EventAnalysisWorkflow the webhook used. Capped per run to bound LLM spend.
Missing API key / provider errors are reported in the result, never swallowed as "no news".
"""
import asyncio
import logging
from typing import Any, Dict, List

from src.data.providers.finnhub_provider import FinnhubProvider
from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

SETTING_ENABLED = "finnhub_poll_enabled"
SETTING_MAX_EVENTS = "finnhub_poll_max_events"
DEFAULT_MAX_EVENTS = 3


class FinnhubPollService:
    def __init__(self, user_id: str, provider=None, webhook=None, settings=None, repo=None):
        self.user_id = user_id
        self.settings = settings or SettingsService(user_id=user_id)
        self.provider = provider or FinnhubProvider(user_id=user_id, settings_service=self.settings)
        if webhook is None:
            from src.services.webhook_service import webhook_service_instance
            webhook = webhook_service_instance
        self.webhook = webhook
        self.repo = repo or TickerUniverseRepository()

    def _max_events(self) -> int:
        try:
            return max(0, int(self.settings.get_setting(SETTING_MAX_EVENTS, DEFAULT_MAX_EVENTS)))
        except (TypeError, ValueError):
            return DEFAULT_MAX_EVENTS

    def _seen_key(self, url: str) -> str:
        import hashlib
        return f"finnhub_poll:seen:{self.user_id}:{hashlib.sha256(url.encode()).hexdigest()}"

    def _already_seen(self, url: str) -> bool:
        r = getattr(self.webhook, "_redis", None)
        try:
            return bool(r and r.exists(self._seen_key(url)))
        except Exception as e:  # unknown => treat as seen, never re-spend LLM on a Redis fault
            logger.warning("FinnhubPollService: seen-check failed (%s); skipping item", e)
            return True

    def _mark_seen(self, url: str) -> None:
        r = getattr(self.webhook, "_redis", None)
        try:
            if r:
                r.set(self._seen_key(url), "1", ex=7 * 86400)
        except Exception as e:
            logger.warning("FinnhubPollService: mark-seen failed: %s", e)

    def collect_new_events(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch news and keep items not seen before (dedupe by url)."""
        from src.services.webhook_service import FinnhubParser
        out: List[Dict[str, Any]] = []
        for t in tickers:
            for item in self.provider.fetch_news(t, limit=3):
                payload = {"event": "news", "ticker": t,
                           "data": {"headline": item.get("title"), "url": item.get("url"), "symbol": t}}
                norm = FinnhubParser.parse(payload)
                url = norm.get("url")
                if not url or self._already_seen(url) or self.webhook._is_duplicate(self.user_id, url=url):
                    continue
                out.append(norm)
        return out

    async def run(self) -> Dict[str, Any]:
        if not self.settings.get_setting(SETTING_ENABLED, False):
            return {"status": "disabled"}
        if not getattr(self.provider, "api_key", None):
            logger.warning("FinnhubPollService: no Finnhub API key configured")
            return {"status": "error", "reason": "missing_api_key"}
        rows = self.repo.get_all(self.user_id, status="active")
        tickers = sorted({r["ticker"] for r in rows})
        events = self.collect_new_events(tickers)
        cap = self._max_events()
        from src.services.workflow_service import EventAnalysisWorkflow
        dispatched = 0
        for norm in events[:cap]:
            if not self.webhook._acquire_concurrency_lock(self.user_id, url=norm.get("url")):
                continue
            self._mark_seen(norm["url"])  # mark first: a failing run must not retry-spend every poll
            await EventAnalysisWorkflow(user_id=self.user_id, event_source="finnhub", event_data=norm).run()
            dispatched += 1
        return {"status": "ok", "tickers": len(tickers), "new": len(events),
                "dispatched": dispatched, "deferred": max(0, len(events) - cap)}


def run_sync(user_id: str) -> Dict[str, Any]:
    return asyncio.run(FinnhubPollService(user_id).run())
