import pytest
from unittest.mock import MagicMock, patch
from src.services.market_news_filter_service import MarketNewsFilterService, MarketFilterResult


def test_clean_url_strips_tracking():
    url = "https://example.com/news/123?utm_source=rss&utm_medium=feed&fbclid=abc123xyz"
    clean = MarketNewsFilterService.clean_url(url)
    assert clean == "https://example.com/news/123"


def test_normalize_title():
    t1 = "TSMC Reports Record Q3 Revenue Growth | Reuters"
    t2 = "TSMC reports record Q3 revenue growth - CNBC"
    n1 = MarketNewsFilterService.normalize_title(t1)
    n2 = MarketNewsFilterService.normalize_title(t2)
    assert n1 == n2 == "tsmc reports record q3 revenue growth"


def test_semantic_deduplication():
    svc = MarketNewsFilterService(user_id="test_user")
    svc._memory_seen_hashes.clear()

    title = "Federal Reserve Cuts Rates by 50 Bps"
    url = "https://bloomberg.com/fed-cuts?utm_source=twitter"

    # First time: not duplicate
    assert not svc.is_semantic_duplicate(title, url)

    # Record seen
    svc.record_seen(title, url)

    # Second time with slight publisher suffix or different tracking: should be duplicate
    dup_title = "Federal Reserve Cuts Rates by 50 Bps | Bloomberg"
    dup_url = "https://bloomberg.com/fed-cuts?utm_source=rss"
    assert svc.is_semantic_duplicate(dup_title, dup_url)


def test_noise_filter_drops_pr_and_lifestyle():
    svc = MarketNewsFilterService(user_id="test_user")
    
    with patch.object(svc, "get_portfolio_holdings", return_value={"TSM", "AAPL"}), \
         patch.object(svc, "get_watchlist_tickers", return_value={"SPY", "QQQ"}):

        # PR Newswire promotional fluff
        res1 = svc.evaluate(
            title="PR Newswire: SmallCo Announces Groundbreaking New Wellness Tea",
            content="A sponsored press release about herbal tea.",
        )
        assert res1.should_drop
        assert res1.category == "low_signal_noise"

        # Lifestyle fluff
        res2 = svc.evaluate(
            title="How to save money and retire early with 5 simple habits",
            content="Personal finance advice from experts.",
        )
        assert res2.should_drop
        assert res2.category == "low_signal_noise"

        # Crypto memecoin
        res3 = svc.evaluate(
            title="New 1000x Dogecoin Moonshot Rival Launches Today",
            content="Meme coin fever strikes crypto traders.",
        )
        assert res3.should_drop
        assert res3.category == "low_signal_noise"


def test_portfolio_holding_news_passes_high_priority():
    svc = MarketNewsFilterService(user_id="test_user")

    with patch.object(svc, "get_portfolio_holdings", return_value={"TSM", "AAPL", "NVDA"}), \
         patch.object(svc, "get_watchlist_tickers", return_value={"SPY"}):

        res = svc.evaluate(
            title="TSM Announces New 2nm Capacity Expansion for Major AI Accelerators",
            content="Taiwan Semiconductor reports surging foundry demand.",
            url="https://reuters.com/tsm-capacity",
        )
        assert not res.should_drop
        assert res.is_relevant
        assert res.relevance_score >= 8.5
        assert "TSM" in res.matched_tickers
        assert res.category == "portfolio_holding"


def test_systemic_macro_news_passes():
    svc = MarketNewsFilterService(user_id="test_user")

    with patch.object(svc, "get_portfolio_holdings", return_value={"TSM", "AAPL"}), \
         patch.object(svc, "get_watchlist_tickers", return_value={"SPY"}):

        res = svc.evaluate(
            title="FOMC Statement: Fed Cuts Interest Rate by 25 Bps Amid Cooling Inflation",
            content="Jerome Powell delivers post-meeting press conference.",
            url="https://wsj.com/fomc-decision",
        )
        assert not res.should_drop
        assert res.is_relevant
        assert res.relevance_score >= 7.5
        assert res.category == "macro_systemic"
        assert res.macro_topic is not None


def test_generic_irrelevant_market_noise_dropped():
    svc = MarketNewsFilterService(user_id="test_user")

    with patch.object(svc, "get_portfolio_holdings", return_value={"TSM", "AAPL"}), \
         patch.object(svc, "get_watchlist_tickers", return_value={"SPY"}):

        res = svc.evaluate(
            title="Local regional grocery chain in Midwest reports Q2 foot traffic",
            content="Retail store sales flat in rural areas.",
        )
        assert res.should_drop
        assert not res.is_relevant
        assert res.category == "unrelated_market_noise"
