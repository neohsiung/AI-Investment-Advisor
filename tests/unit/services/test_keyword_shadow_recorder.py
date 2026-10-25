"""Keyword shadow recorder: counts where the live and shadow keyword rules agree or differ, never raises.
關鍵字 shadow 紀錄器：計數正式規則與 shadow 規則一致或不一致的次數，永不拋錯。"""
from datetime import datetime, timezone
from unittest.mock import patch

from src.services import keyword_shadow_recorder as rec

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


class FakeRedis:
    """Records writes; ``pipeline()`` returns itself so one round trip is checked via ``executed``."""

    def __init__(self):
        self.h = {}
        self.expiry = {}
        self.executed = 0

    def pipeline(self, transaction=False):
        return self

    def execute(self):
        self.executed += 1

    def hincrby(self, key, field, n=1):
        self.h.setdefault(key, {})
        self.h[key][field] = self.h[key].get(field, 0) + n

    def expire(self, key, seconds):
        self.expiry[key] = seconds

    def hgetall(self, key):
        return {k: str(v) for k, v in self.h.get(key, {}).items()}


def test_outcome_fields():
    assert rec.outcome_fields("ticker_news", True, False) == [
        "ticker_news:scanned", "ticker_news:live", "ticker_news:live_only"]
    assert rec.outcome_fields("global_event", True, True) == [
        "global_event:scanned", "global_event:live", "global_event:shadow"]
    assert rec.outcome_fields("global_event", False, False) == ["global_event:scanned"]


def test_record_counts_per_day_and_sets_ttl():
    r = FakeRedis()
    with patch.object(rec, "get_redis_sync", return_value=r):
        rec.record("ticker_news", True, False, "SPY", now=NOW)
        rec.record("ticker_news", True, True, "JPM", now=NOW)
    key = "sentinel:kw_shadow:2026-10-25"
    assert r.h[key] == {"ticker_news:scanned": 2, "ticker_news:live": 2,
                        "ticker_news:live_only": 1, "ticker_news:shadow": 1}
    assert r.expiry[key] == rec.TTL_SECONDS
    assert r.executed == 2   # one round trip per record, not one per counter


def test_record_never_raises_when_redis_fails(caplog):
    with patch.object(rec, "get_redis_sync", side_effect=ConnectionError("down")):
        rec.record("ticker_news", True, False, "SPY", now=NOW)
    assert "keyword shadow" in caplog.text


def test_summary_sums_the_last_n_days():
    r = FakeRedis()
    r.h["sentinel:kw_shadow:2026-10-25"] = {"ticker_news:live": 3}
    r.h["sentinel:kw_shadow:2026-10-24"] = {"ticker_news:live": 2, "ticker_news:shadow": 1}
    r.h["sentinel:kw_shadow:2026-10-17"] = {"ticker_news:live": 99}   # outside a 7-day window
    with patch.object(rec, "get_redis_sync", return_value=r):
        assert rec.summary(days=7, now=NOW) == {"ticker_news:live": 5, "ticker_news:shadow": 1}


def test_compare_records_live_and_shadow_outcomes():
    with patch.object(rec, "record") as record:
        rec.compare("global_event", 0.6, 1.0, lambda: 0.5, "headline")
    record.assert_called_once_with("global_event", True, False, "headline")


def test_compare_keywords_scores_each_text_with_both_rules():
    from src.domain.entities import RiskKeyword
    kws = [RiskKeyword(keyword="es", weight=1.0, source="trends"), RiskKeyword(keyword="crash", weight=0.9)]
    with patch.object(rec, "record") as record:
        rec.compare_keywords("ticker_news", 0.6, ["ES futures slide", "Markets crash"], kws, "SPY")
    record.assert_called_once_with("ticker_news", True, False, "SPY")   # best live 1.0; best shadow 0.5


def test_compare_never_raises_and_records_nothing_when_scoring_fails(caplog):
    def boom():
        raise TypeError("bad keyword object")
    with patch.object(rec, "record") as record:
        rec.compare("webhook_news", 0.6, 1.0, boom, "x")
    record.assert_not_called()
    assert "keyword shadow" in caplog.text
