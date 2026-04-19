import pytest
import pytz
import pandas as pd
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

from src.utils.market_clock import MarketClock

@pytest.fixture
def mock_mcal():
    with patch('src.utils.market_clock.mcal.get_calendar') as mock_get_cal:
        mock_cal = MagicMock()
        mock_get_cal.return_value = mock_cal
        
        # Create a mock schedule DataFrame
        today = datetime.now(pytz.utc).date()
        mock_open = pd.Timestamp(datetime.now(pytz.utc) - timedelta(hours=1)) # Opened 1 hr ago
        mock_close = pd.Timestamp(datetime.now(pytz.utc) + timedelta(hours=5)) # Closes in 5 hrs
        
        df = pd.DataFrame({
            'market_open': [mock_open],
            'market_close': [mock_close]
        }, index=[pd.Timestamp(today)])
        
        mock_cal.schedule.return_value = df
        yield mock_cal

def test_market_clock_init_default():
    clock = MarketClock()
    assert clock.exchange_name == 'NYSE'
    assert clock.tz.zone == 'US/Eastern'

def test_market_clock_is_market_open(mock_mcal):
    clock = MarketClock()
    assert clock.is_market_open() is True
    assert clock.is_market_open(buffer_minutes=10) is True

def test_market_clock_is_market_open_closed(mock_mcal):
    clock = MarketClock()
    # Mock a closed schedule (empty dataframe like weekend or holiday)
    mock_mcal.schedule.return_value = pd.DataFrame()
    assert clock.is_market_open() is False

def test_market_clock_get_market_status(mock_mcal):
    with patch("src.utils.market_clock.datetime") as mock_dt:
        # Mock what now() calls return
        naive_now = datetime(2023, 1, 1, 12, 0, 0)
        est = pytz.timezone('US/Eastern')
        mock_now_est = est.localize(naive_now)
        mock_utc_now = pytz.utc.localize(datetime(2023, 1, 1, 17, 0, 0))
        
        # Make datetime.now(self.tz) return mock_now_est, and datetime.now(pytz.utc) return mock_utc_now
        def mock_now(tz=None):
            if tz == pytz.utc: return mock_utc_now
            return mock_now_est
            
        mock_dt.now.side_effect = mock_now
        
        clock = MarketClock()
        status = clock.get_market_status()
        
        assert "is_open" in status
        assert "is_dst" in status
        assert status["timezone"] == "US/Eastern"
        assert status["exchange"] == "NYSE"
        assert "next_open" in status
        assert "next_close" in status
        assert "current_time" in status

def test_market_clock_get_nyse_time():
    nyse_time = MarketClock.get_nyse_time()
    assert nyse_time.tzinfo.zone == 'US/Eastern'
