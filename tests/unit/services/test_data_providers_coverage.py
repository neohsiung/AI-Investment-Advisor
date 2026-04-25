"""
Tests for AlphaVantageProvider, FinnhubProvider, TiingoProvider - coverage improvement.
補充 data providers 的測試覆蓋率。
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch, Mock
from src.data.providers.alpha_vantage_provider import AlphaVantageProvider
from src.data.providers.finnhub_provider import FinnhubProvider
from src.data.providers.tiingo_provider import TiingoProvider


# ─────────────────────────────────────────────
# AlphaVantageProvider Tests
# ─────────────────────────────────────────────

class TestAlphaVantageProviderInit:
    """Test AlphaVantageProvider initialization."""

    def test_init_with_api_key(self):
        with patch("src.data.providers.alpha_vantage_provider.SettingsService"):
            provider = AlphaVantageProvider(api_key="test_key_123")
            assert provider.api_key == "test_key_123"
            assert provider.base_url == "https://www.alphavantage.co/query"

    def test_init_gets_api_key_from_settings(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_alpha_vantage_api_key": "settings_key"}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider()
            assert provider.api_key == "settings_key"

    def test_init_fallback_api_key(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"ALPHA_VANTAGE_API_KEY": "fallback_key"}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider()
            assert provider.api_key == "fallback_key"


class TestAlphaVantageProviderFetchCurrentPrices:
    """Test AlphaVantageProvider.fetch_current_prices."""

    def test_fetch_current_prices_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "Global Quote": {"05. price": "150.25"}
            }
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert "AAPL" in result
            assert result["AAPL"] == 150.25

    def test_fetch_current_prices_empty_response(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"Global Quote": {}}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}

    def test_fetch_current_prices_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            with patch("requests.get", side_effect=Exception("Network error")):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}

    def test_fetch_current_prices_multiple_tickers(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"Global Quote": {"05. price": "200.00"}}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL", "MSFT"])
            assert len(result) == 2


class TestAlphaVantageProviderFetchHistory:
    """Test AlphaVantageProvider.fetch_history."""

    def test_fetch_history_success(self):
        import datetime
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            # Use a recent date so it passes the start_date filter
            recent_date = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
            mock_resp.json.return_value = {
                "Time Series (Daily)": {
                    recent_date: {
                        "1. open": "150.0",
                        "2. high": "155.0",
                        "3. low": "148.0",
                        "4. close": "152.0",
                        "5. volume": "1000000"
                    }
                }
            }
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert not result.empty
            assert "Close" in result.columns

    def test_fetch_history_empty_response(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"Time Series (Daily)": {}}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            with patch("requests.get", side_effect=Exception("API error")):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_with_days(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"Time Series (Daily)": {}}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL", days=30)
            assert isinstance(result, pd.DataFrame)


class TestAlphaVantageProviderFetchInfo:
    """Test AlphaVantageProvider.fetch_info."""

    def test_fetch_info_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"Symbol": "AAPL", "Name": "Apple Inc"}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_info("AAPL")
            assert result == {"Symbol": "AAPL", "Name": "Apple Inc"}

    def test_fetch_info_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            with patch("requests.get", side_effect=Exception("Error")):
                result = provider.fetch_info("AAPL")
            assert result == {}


class TestAlphaVantageProviderFetchNews:
    """Test AlphaVantageProvider.fetch_news."""

    def test_fetch_news_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "feed": [
                    {
                        "title": "Apple News",
                        "url": "https://example.com",
                        "time_published": "20240115T120000",
                        "summary": "Summary",
                        "overall_sentiment_score": 0.5,
                        "overall_sentiment_label": "Bullish"
                    }
                ]
            }
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_news("AAPL", limit=5)
            assert len(result) == 1
            assert result[0]["title"] == "Apple News"
            assert result[0]["source"] == "AlphaVantage"

    def test_fetch_news_empty_feed(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"feed": []}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_news("AAPL")
            assert result == []

    def test_fetch_news_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.alpha_vantage_provider.SettingsService", return_value=mock_settings):
            provider = AlphaVantageProvider(api_key="test_key")
            with patch("requests.get", side_effect=Exception("Error")):
                result = provider.fetch_news("AAPL")
            assert result == []


# ─────────────────────────────────────────────
# FinnhubProvider Tests
# ─────────────────────────────────────────────

class TestFinnhubProviderInit:
    """Test FinnhubProvider initialization."""

    def test_init_default(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            assert provider.api_key == "fh_key"
            assert provider.base_url == "https://finnhub.io/api/v1"

    def test_init_with_user_id(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider(user_id="user123")
            assert provider.user_id == "user123"


class TestFinnhubProviderFetchCurrentPrices:
    """Test FinnhubProvider.fetch_current_prices."""

    def test_fetch_current_prices_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"c": 175.50, "h": 180.0, "l": 170.0}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert "AAPL" in result
            assert result["AAPL"] == 175.50

    def test_fetch_current_prices_no_price_field(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}

    def test_fetch_current_prices_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            with patch("requests.get", side_effect=Exception("Network error")):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}


class TestFinnhubProviderFetchHistory:
    """Test FinnhubProvider.fetch_history."""

    def test_fetch_history_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "s": "ok",
                "t": [1705276800],
                "o": [150.0],
                "h": [155.0],
                "l": [148.0],
                "c": [152.0],
                "v": [1000000]
            }
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert not result.empty
            assert "Close" in result.columns

    def test_fetch_history_no_data(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"s": "no_data"}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            with patch("requests.get", side_effect=Exception("API error")):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_with_days(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"s": "no_data"}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL", days=90)
            assert isinstance(result, pd.DataFrame)


class TestFinnhubProviderFetchInfo:
    """Test FinnhubProvider.fetch_info."""

    def test_fetch_info_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"name": "Apple Inc", "ticker": "AAPL"}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_info("AAPL")
            assert result == {"name": "Apple Inc", "ticker": "AAPL"}

    def test_fetch_info_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            with patch("requests.get", side_effect=Exception("Error")):
                result = provider.fetch_info("AAPL")
            assert result == {}


class TestFinnhubProviderFetchNews:
    """Test FinnhubProvider.fetch_news."""

    def test_fetch_news_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {
                    "headline": "Apple Reports Earnings",
                    "url": "https://example.com",
                    "datetime": 1705276800,
                    "summary": "Apple beats estimates",
                    "related": "AAPL"
                }
            ]
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_news("AAPL", limit=5)
            assert len(result) == 1
            assert result[0]["title"] == "Apple Reports Earnings"
            assert result[0]["source"] == "Finnhub"

    def test_fetch_news_non_list_response(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": "not found"}
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_news("AAPL")
            assert result == []

    def test_fetch_news_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            with patch("requests.get", side_effect=Exception("Error")):
                result = provider.fetch_news("AAPL")
            assert result == []


class TestFinnhubProviderGetSentiment:
    """Test FinnhubProvider.get_sentiment."""

    def test_get_sentiment_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_finnhub_api_key": "fh_key"}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"buzz": {"articlesInLastWeek": 10}, "sentiment": {"bearishPercent": 0.3}}
            with patch("requests.get", return_value=mock_resp):
                result = provider.get_sentiment("AAPL")
            assert "buzz" in result

    def test_get_sentiment_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.finnhub_provider.SettingsService", return_value=mock_settings):
            provider = FinnhubProvider()
            with patch("requests.get", side_effect=Exception("Error")):
                result = provider.get_sentiment("AAPL")
            assert result == {}


# ─────────────────────────────────────────────
# TiingoProvider Tests
# ─────────────────────────────────────────────

class TestTiingoProviderInit:
    """Test TiingoProvider initialization."""

    def test_init_with_api_key(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider(api_key="tiingo_key")
            assert provider.api_key == "tiingo_key"
            assert provider.base_url == "https://api.tiingo.com"

    def test_init_gets_key_from_settings(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "settings_tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            assert provider.api_key == "settings_tiingo_key"

    def test_init_no_api_key_logs_warning(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            assert provider.api_key is None


class TestTiingoProviderFetchCurrentPrices:
    """Test TiingoProvider.fetch_current_prices."""

    def test_fetch_current_prices_no_api_key_returns_empty(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            result = provider.fetch_current_prices(["AAPL"])
            assert result == {}

    def test_fetch_current_prices_empty_tickers_returns_empty(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            result = provider.fetch_current_prices([])
            assert result == {}

    def test_fetch_current_prices_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [
                {"ticker": "AAPL", "last": 175.50},
                {"ticker": "MSFT", "last": 380.00}
            ]
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL", "MSFT"])
            assert result["AAPL"] == 175.50
            assert result["MSFT"] == 380.00

    def test_fetch_current_prices_uses_tngo_last(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [
                {"ticker": "AAPL", "last": None, "tngoLast": 176.00}
            ]
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert result["AAPL"] == 176.00

    def test_fetch_current_prices_non_200_returns_empty(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}

    def test_fetch_current_prices_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            with patch("requests.get", side_effect=Exception("Network error")):
                result = provider.fetch_current_prices(["AAPL"])
            assert result == {}


class TestTiingoProviderFetchHistory:
    """Test TiingoProvider.fetch_history."""

    def test_fetch_history_no_api_key_returns_empty(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_success(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            # Tiingo uses adjOpen/adjHigh/adjLow/adjClose/adjVolume
            mock_resp.json.return_value = [
                {
                    "date": "2024-01-15T00:00:00+00:00",
                    "adjOpen": 150.0,
                    "adjHigh": 155.0,
                    "adjLow": 148.0,
                    "adjClose": 152.0,
                    "adjVolume": 1000000
                }
            ]
            with patch("requests.get", return_value=mock_resp):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert not result.empty

    def test_fetch_history_exception(self):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_tiingo_api_key": "tiingo_key"}
        with patch("src.data.providers.tiingo_provider.SettingsService", return_value=mock_settings):
            provider = TiingoProvider()
            with patch("requests.get", side_effect=Exception("API error")):
                result = provider.fetch_history("AAPL")
            assert isinstance(result, pd.DataFrame)
            assert result.empty
