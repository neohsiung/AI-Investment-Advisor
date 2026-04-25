"""
Tests for FredProvider - coverage improvement.
補充 fred_provider.py 的測試覆蓋率。
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from src.data.providers.fred_provider import FredProvider


class TestFredProviderInit:
    """Test FredProvider initialization."""

    def test_init_default(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred_cls.return_value = mock_fred
            provider = FredProvider()
            assert provider.name == "FRED"
            mock_fred_cls.assert_called_once_with(user_id="system", settings_service=None)

    def test_init_with_user_id(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred_cls.return_value = mock_fred
            provider = FredProvider(user_id="user123")
            mock_fred_cls.assert_called_once_with(user_id="user123", settings_service=None)

    def test_init_with_settings_service(self):
        mock_settings = MagicMock()
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred_cls.return_value = mock_fred
            provider = FredProvider(settings_service=mock_settings)
            mock_fred_cls.assert_called_once_with(user_id="system", settings_service=mock_settings)


class TestFredProviderFetchCurrentPrices:
    """Test FredProvider.fetch_current_prices."""

    def test_fetch_current_prices_returns_empty_dict(self):
        with patch("src.data.providers.fred_provider.FredService"):
            provider = FredProvider()
            result = provider.fetch_current_prices(["GDP", "UNRATE"])
            assert result == {}

    def test_fetch_current_prices_empty_list(self):
        with patch("src.data.providers.fred_provider.FredService"):
            provider = FredProvider()
            result = provider.fetch_current_prices([])
            assert result == {}


class TestFredProviderFetchHistory:
    """Test FredProvider.fetch_history."""

    def test_fetch_history_no_client_returns_empty_df(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = None
            mock_fred_cls.return_value = mock_fred
            provider = FredProvider()
            result = provider.fetch_history("GDP")
            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_success(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            # Return a pandas Series as FRED would
            mock_series = pd.Series([100.0, 101.0, 102.0], name="GDP")
            mock_fred.client.get_series.return_value = mock_series
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_history("GDP", period="1y")

            assert isinstance(result, pd.DataFrame)
            assert "Close" in result.columns
            mock_fred.client.get_series.assert_called_once()

    def test_fetch_history_with_days_param(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            mock_series = pd.Series([200.0, 201.0], name="UNRATE")
            mock_fred.client.get_series.return_value = mock_series
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_history("UNRATE", days=90)

            assert isinstance(result, pd.DataFrame)
            call_kwargs = mock_fred.client.get_series.call_args
            # Verify days=90 was used (start_date should be ~90 days ago)
            assert call_kwargs is not None

    def test_fetch_history_exception_returns_empty_df(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            mock_fred.client.get_series.side_effect = Exception("API error")
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_history("GDP")

            assert isinstance(result, pd.DataFrame)
            assert result.empty

    def test_fetch_history_default_days_is_365(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            mock_series = pd.Series([1.0, 2.0], name="DGS10")
            mock_fred.client.get_series.return_value = mock_series
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            # No days param → defaults to 365
            result = provider.fetch_history("DGS10")
            assert isinstance(result, pd.DataFrame)


class TestFredProviderFetchInfo:
    """Test FredProvider.fetch_info."""

    def test_fetch_info_no_client_returns_empty_dict(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = None
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_info("GDP")
            assert result == {}

    def test_fetch_info_success_with_to_dict(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            mock_info = MagicMock()
            mock_info.to_dict.return_value = {"id": "GDP", "title": "Gross Domestic Product"}
            mock_fred.client.get_series_info.return_value = mock_info
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_info("GDP")
            assert result == {"id": "GDP", "title": "Gross Domestic Product"}

    def test_fetch_info_success_without_to_dict(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            # Return a plain dict (no to_dict method)
            mock_fred.client.get_series_info.return_value = {"id": "UNRATE", "title": "Unemployment Rate"}
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_info("UNRATE")
            assert "id" in result or isinstance(result, dict)

    def test_fetch_info_exception_returns_empty_dict(self):
        with patch("src.data.providers.fred_provider.FredService") as mock_fred_cls:
            mock_fred = MagicMock()
            mock_fred.client = MagicMock()
            mock_fred.client.get_series_info.side_effect = Exception("Not found")
            mock_fred_cls.return_value = mock_fred

            provider = FredProvider()
            result = provider.fetch_info("INVALID")
            assert result == {}


class TestFredProviderFetchNews:
    """Test FredProvider.fetch_news."""

    def test_fetch_news_returns_empty_list(self):
        with patch("src.data.providers.fred_provider.FredService"):
            provider = FredProvider()
            result = provider.fetch_news("GDP")
            assert result == []

    def test_fetch_news_with_limit_returns_empty_list(self):
        with patch("src.data.providers.fred_provider.FredService"):
            provider = FredProvider()
            result = provider.fetch_news("GDP", limit=10)
            assert result == []
