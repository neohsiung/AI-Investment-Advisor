"""
Unit tests for the webhook source parsers.
Webhook 來源解析器單元測試。

These are pure static functions with no I/O — the cheapest meaningful coverage
in the service, and the layer every inbound integration passes through before
anything else looks at the payload. A parser silently returning "UNKNOWN" for a
ticker is the kind of bug that surfaces three hops later as a mis-attributed
event, so the fallbacks are asserted explicitly rather than assumed.

這些都是純靜態函式、沒有 I/O。所有入站整合都先經過這一層，parser 靜默把
ticker 解成 "UNKNOWN" 會在三個環節之後才以「事件歸錯標的」的形式爆出來，
所以這裡把每個 fallback 都明確斷言，而不是假設它對。
"""
import hashlib

import pytest

from src.services.webhook_service import (
    SOURCE_PARSERS,
    BaseSourceParser,
    FinnhubParser,
    MktRecapParser,
    N8nParser,
    PolygonParser,
    RssBridgeParser,
    SkillLearningParser,
    TradingViewParser,
)


class TestBaseSourceParser:
    def test_returns_payload_unchanged(self):
        payload = {"anything": 1}
        assert BaseSourceParser.parse(payload) is payload


class TestMktRecapParser:
    def test_full_payload(self):
        out = MktRecapParser.parse(
            {"ticker": "AAPL", "price": 190.5, "alert_name": "Gap up"}
        )
        assert out == {
            "type": "MARKET_SPIKE", "ticker": "AAPL",
            "value": 190.5, "msg": "Gap up",
        }

    def test_falls_back_to_volume_when_price_absent(self):
        out = MktRecapParser.parse({"ticker": "AAPL", "volume": 1_000_000})
        assert out["value"] == 1_000_000

    def test_defaults(self):
        out = MktRecapParser.parse({})
        assert out["ticker"] == "UNKNOWN"
        assert out["value"] is None
        assert out["msg"] == "MktRecap Trigger"

    def test_zero_price_falls_through_to_volume(self):
        """`or` on a falsy price means 0 is treated as absent — documented, not endorsed."""
        out = MktRecapParser.parse({"price": 0, "volume": 42})
        assert out["value"] == 42


class TestTradingViewParser:
    def test_full_payload(self):
        out = TradingViewParser.parse(
            {"ticker": "TSLA", "signal": "BUY", "comment": "MACD cross"}
        )
        assert out == {
            "type": "TECHNICAL_SIGNAL", "ticker": "TSLA",
            "signal": "BUY", "msg": "MACD cross",
        }

    def test_defaults(self):
        out = TradingViewParser.parse({})
        assert out["ticker"] is None
        assert out["signal"] is None
        assert out["msg"] == "TV Alert"


class TestRssBridgeParser:
    def test_prefers_title_over_description(self):
        out = RssBridgeParser.parse(
            {"title": "Fed holds", "description": "longer text", "link": "http://x/1"}
        )
        assert out == {"type": "NEWS_ALERT", "msg": "Fed holds", "url": "http://x/1"}

    def test_falls_back_to_description(self):
        out = RssBridgeParser.parse({"description": "longer text"})
        assert out["msg"] == "longer text"

    def test_defaults(self):
        out = RssBridgeParser.parse({})
        assert out["msg"] == "New RSS Item"
        assert out["url"] is None


class TestFinnhubParser:
    def test_news_event_uses_headline(self):
        out = FinnhubParser.parse({
            "event": "news", "ticker": "NVDA",
            "data": {"headline": "Chip demand surges", "url": "http://n/1"},
        })
        assert out["type"] == "FINANCIAL_EVENT"
        assert out["ticker"] == "NVDA"
        assert out["msg"] == "Chip demand surges"
        assert out["url"] == "http://n/1"

    def test_earnings_event_formats_quarter_and_eps(self):
        out = FinnhubParser.parse({
            "event": "earnings", "ticker": "MSFT",
            "data": {"quarter": 3, "eps": 2.99},
        })
        assert out["msg"] == "Earnings Alert for MSFT: Q3 EPS=2.99"

    def test_data_as_list_uses_first_element(self):
        out = FinnhubParser.parse({
            "event": "news", "data": [{"symbol": "AMD", "headline": "First"},
                                      {"symbol": "INTC", "headline": "Second"}],
        })
        assert out["ticker"] == "AMD"
        assert out["msg"] == "First"

    def test_empty_list_data_yields_unknown_ticker(self):
        out = FinnhubParser.parse({"event": "news", "data": []})
        assert out["ticker"] == "UNKNOWN"

    def test_ticker_falls_back_to_data_symbol(self):
        out = FinnhubParser.parse({"event": "news", "data": {"symbol": "GOOG"}})
        assert out["ticker"] == "GOOG"

    def test_unrecognized_event_keeps_generic_message(self):
        out = FinnhubParser.parse({"event": "ipo", "ticker": "ABC", "data": {}})
        assert out["msg"] == "Finnhub Alert: ipo"

    def test_news_without_headline_falls_back(self):
        out = FinnhubParser.parse({"event": "news", "ticker": "ABC", "data": {}})
        assert out["msg"] == "News Alert for ABC"

    def test_defaults_to_news_event(self):
        """No `event` key means news — asserted so the default can't drift silently."""
        out = FinnhubParser.parse({"data": {"headline": "H"}})
        assert out["msg"] == "H"

    def test_non_dict_non_list_data_is_ignored(self):
        out = FinnhubParser.parse({"event": "news", "ticker": "X", "data": "garbage"})
        assert out["ticker"] == "X"
        assert out["url"] is None


class TestN8nParser:
    def test_unwraps_body_when_present(self):
        out = N8nParser.parse({"body": {"ticker": "AAPL", "message": "from body"}})
        assert out["ticker"] == "AAPL"
        assert out["msg"] == "from body"

    def test_non_dict_body_is_not_unwrapped(self):
        out = N8nParser.parse({"body": "not-a-dict", "ticker": "TOP"})
        assert out["ticker"] == "TOP"

    def test_signal_id_derived_from_link(self):
        url = "http://example.com/a"
        out = N8nParser.parse({"link": url})
        assert out["signal_id"] == f"rss_{hashlib.sha256(url.encode()).hexdigest()}"
        assert out["url"] == url

    def test_signal_id_derived_from_url_when_link_absent(self):
        url = "http://example.com/b"
        out = N8nParser.parse({"url": url})
        assert out["signal_id"] == f"rss_{hashlib.sha256(url.encode()).hexdigest()}"

    def test_explicit_event_id_wins_over_derived(self):
        out = N8nParser.parse({"event_id": "given", "link": "http://example.com/c"})
        assert out["signal_id"] == "given"

    def test_no_url_leaves_signal_id_none(self):
        out = N8nParser.parse({"message": "no link here"})
        assert out["signal_id"] is None

    def test_message_falls_back_to_msg_then_default(self):
        assert N8nParser.parse({"msg": "short form"})["msg"] == "short form"
        assert N8nParser.parse({})["msg"] == "n8n Triggered Event"

    def test_defaults(self):
        out = N8nParser.parse({})
        assert out["type"] == "N8N_AUTOMATION"
        assert out["ticker"] == "GLOBAL"
        assert out["value"] is None


class TestPolygonParser:
    def test_trade_event(self):
        out = PolygonParser.parse({"ev": "T", "sym": "AAPL", "p": 190.1, "s": 100})
        assert out["type"] == "POLYGON_EVENT"
        assert out["ev"] == "T"
        assert out["msg"] == "Trade Event for AAPL: Price=190.1 Size=100"

    def test_aggregate_event(self):
        out = PolygonParser.parse({"ev": "A", "sym": "AAPL", "c": 191.0, "v": 5000})
        assert out["msg"] == "Aggregate Alert for AAPL: Close=191.0 Vol=5000"

    def test_list_payload_uses_first_event(self):
        out = PolygonParser.parse([{"ev": "T", "sym": "FIRST"}, {"ev": "A", "sym": "SECOND"}])
        assert out["ticker"] == "FIRST"

    def test_empty_list_falls_through_to_payload(self):
        """An empty list is falsy, so `payload[0]` is skipped and .get() would fail
        on a list — assert the documented behaviour rather than guess."""
        with pytest.raises(AttributeError):
            PolygonParser.parse([])

    def test_unknown_event_type_generic_message(self):
        out = PolygonParser.parse({"ev": "Q", "sym": "AAPL"})
        assert out["msg"] == "Polygon.io Alert: Q for AAPL"

    def test_defaults(self):
        out = PolygonParser.parse({})
        assert out["ticker"] == "UNKNOWN"
        assert out["ev"] == "unknown"


class TestSkillLearningParser:
    def test_prefers_content_over_other_text_fields(self):
        out = SkillLearningParser.parse({
            "content": "primary", "article_text": "secondary", "transcript": "tertiary",
        })
        assert out["content"] == "primary"

    @pytest.mark.parametrize("key", ["article_text", "transcript", "text"])
    def test_content_fallback_chain(self, key):
        assert SkillLearningParser.parse({key: "value"})["content"] == "value"

    @pytest.mark.parametrize("key", ["source_url", "article_url", "audioUrl", "url"])
    def test_source_url_fallback_chain(self, key):
        assert SkillLearningParser.parse({key: "http://u"})["source_url"] == "http://u"

    def test_podcast_name_used_as_source_name(self):
        out = SkillLearningParser.parse({"podcastName": "All-In"})
        assert out["source_name"] == "All-In"

    def test_defaults(self):
        out = SkillLearningParser.parse({})
        assert out["type"] == "SKILL_LEARNING"
        assert out["content"] == ""
        assert out["source_url"] == ""
        assert out["source_type"] == "article"
        assert out["source_name"] == ""


class TestSourceParserRegistry:
    @pytest.mark.parametrize("source,expected", [
        ("mktrecap", MktRecapParser),
        ("tradingview", TradingViewParser),
        ("tradingview_alerts", TradingViewParser),
        ("rss", RssBridgeParser),
        ("rss_bridge", RssBridgeParser),
        ("ifttt", RssBridgeParser),
        ("finnhub", FinnhubParser),
        ("n8n", N8nParser),
        ("make", N8nParser),
        ("pipedream", N8nParser),
        ("skill_learning", SkillLearningParser),
        ("skill-learning", SkillLearningParser),
        ("polygon", PolygonParser),
    ])
    def test_registry_mapping(self, source, expected):
        assert SOURCE_PARSERS[source] is expected

    def test_unknown_source_absent(self):
        """Callers fall back to BaseSourceParser; the registry must not invent entries."""
        assert "definitely-not-a-source" not in SOURCE_PARSERS
