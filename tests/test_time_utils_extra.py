
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime as dt_class, timedelta
import pytz
import os
from freezegun import freeze_time
from src.utils.time_utils import (
    get_db_timezone,
    get_timezone,
    get_current_time,
    format_time,
    get_current_date_str,
    convert_user_time_to_system_time,
    get_current_utc_time,
    DEFAULT_TIMEZONE
)

class TestTimeUtilsCoverage:
    
    @patch('src.utils.time_utils.get_db_connection')
    def test_get_db_timezone_found(self, mock_conn):
        # Mock DB return
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ["Europe/London"]
        mock_conn.return_value.execute.return_value = mock_result
        
        tz = get_db_timezone()
        assert tz == "Europe/London"
        
    @patch('src.utils.time_utils.get_db_connection')
    def test_get_db_timezone_none(self, mock_conn):
        # Mock DB empty
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.return_value.execute.return_value = mock_result
        
        tz = get_db_timezone()
        assert tz is None

    @patch('src.utils.time_utils.get_db_connection')
    def test_get_db_timezone_error(self, mock_conn):
        mock_conn.side_effect = Exception("DB Fail")
        tz = get_db_timezone()
        assert tz is None

    @patch('src.utils.time_utils.get_db_timezone')
    def test_get_timezone_db_priority(self, mock_db_tz):
        mock_db_tz.return_value = "Europe/Paris"
        tz = get_timezone()
        assert tz.zone == "Europe/Paris"

    @patch('src.utils.time_utils.get_db_timezone')
    def test_get_timezone_env(self, mock_db_tz):
        mock_db_tz.return_value = None
        with patch.dict(os.environ, {"TIMEZONE": "Australia/Sydney"}):
            tz = get_timezone()
            assert tz.zone == "Australia/Sydney"
            
    @patch('src.utils.time_utils.get_db_timezone')
    def test_get_timezone_default(self, mock_db_tz):
        mock_db_tz.return_value = None
        # Ensure env is clear or different
        with patch.dict(os.environ, {}, clear=True):
             tz = get_timezone()
             assert tz.zone == DEFAULT_TIMEZONE

    @patch('src.utils.time_utils.get_db_timezone')
    def test_get_timezone_invalid(self, mock_db_tz):
        mock_db_tz.return_value = None
        with patch.dict(os.environ, {"TIMEZONE": "INVALID_TZ"}):
            tz = get_timezone()
            assert tz.zone == DEFAULT_TIMEZONE

    def test_get_current_time(self):
        t = get_current_time()
        assert t.tzinfo is not None

    def test_format_time(self):
        d = dt_class(2023, 1, 1, 12, 0, 0)
        assert format_time(d, "%Y-%m-%d") == "2023-01-01"
        assert len(format_time()) > 0

    def test_get_current_date_str(self):
        with freeze_time("2023-12-25 12:00:00"):
             s = get_current_date_str()
             # Result depends on timezone, but should contain date part
             assert "2023-12-25" in s or "2023-12-26" in s

    def test_get_current_utc_time(self):
        with freeze_time("2023-01-01 12:00:00"):
            t = get_current_utc_time()
            assert t.tzinfo == pytz.utc
            assert t.year == 2023

    @patch('src.utils.time_utils.get_timezone')
    def test_convert_user_time_to_system_time(self, mock_get_tz):
        # Scenario: User is in UTC+8 (Taiwan)
        # System is UTC
        # User wants job at "08:00" (which is 00:00 UTC)
        mock_get_tz.return_value = pytz.timezone("Asia/Taipei")
        
        with freeze_time("2023-01-01 12:00:00"):
            utc_time_str, offset = convert_user_time_to_system_time("08:00")
            
            # 08:00 CST is 00:00 UTC same day
            assert utc_time_str == "00:00"
            assert offset == 0
        
    @patch('src.utils.time_utils.get_timezone')
    def test_convert_user_time_to_system_time_cross_day(self, mock_get_tz):
        # Scenario: User in Tokyo (UTC+9)
        # User time "01:00" => UTC "16:00" (Previous Day)
        # If user sets "01:00", it means 01:00 local time.
        # Tokyo 01:00 Jan 2 = UTC 16:00 Jan 1.
        
        mock_get_tz.return_value = pytz.timezone("Asia/Tokyo")
        
        # We freeze at Jan 2 noon Tokyo time
        with freeze_time("2023-01-02 12:00:00", tz_offset=9):
            utc_time_str, offset = convert_user_time_to_system_time("01:00")
            
            # The function calculates day offset relative to NOW (Jan 2 Tokyo).
            # Target is Jan 2 01:00 Tokyo -> Jan 1 16:00 UTC.
            # Day diff = UTC date (Jan 1) - User date (Jan 2) = -1
            
            assert utc_time_str == "16:00"
            assert offset == -1

    def test_convert_user_time_error(self):
        # Invalid time string
        res, off = convert_user_time_to_system_time("INVALID")
        assert res == "INVALID"
        assert off == 0
