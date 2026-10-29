"""MarketClock.session_today: is today a NYSE trading day, on the New York date.
Only a real exchange calendar may answer. Without one it says "unknown", never a weekday guess:
a holiday shown as an open day is a wrong fact about a system that moves real money.
只有真的交易所日曆能回答；沒有日曆就回 None，不退回只判週末——把假日說成開市日，是對動真錢的系統說錯事實。
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.utils.market_clock import MarketClock

# 2026 NYSE: Thanksgiving is Thursday 11-26 (closed), 11-27 is a half day (open), Christmas Friday 12-25 (closed).
CASES = [
    (datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc), False),   # Thanksgiving
    (datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc), True),    # half day still trades
    (datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc), False),   # Christmas
    (datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc), False),   # Saturday
    (datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc), True),     # ordinary Monday
]


@pytest.mark.parametrize("now,expected", CASES)
def test_session_today_follows_the_exchange_calendar(now, expected):
    assert MarketClock().session_today(now) is expected


def test_session_today_uses_the_new_york_date_not_utc():
    # 2026-11-27 02:00 UTC is still Thanksgiving evening in New York: closed.
    assert MarketClock().session_today(datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)) is False


def test_session_today_is_unknown_without_a_calendar():
    clock = MarketClock()
    clock.nyse = None
    # a Saturday and a holiday must not become "open" or "closed" guesses
    assert clock.session_today(datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)) is None
    assert clock.session_today(datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)) is None
