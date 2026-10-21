"""K1 clear-date projection (pure). The watchdog's K1 is (30-day billed LLM cost x 365/30 + subscriptions x 12) / NAV;
this answers "on which future day does that ratio fall to the threshold, if daily spend from now on is `rate`?".
K1 預計解除日（純函式）：K1＝(近 30 日計費 LLM 成本 × 365/30 ＋ 訂閱 × 12) ÷ 淨值；本函式回答「若今日起每日花費為 rate，
哪一天比率會回到門檻以下」。

The window for day d is d-29 .. d (today included), the same as LiteLLMSpendService.get_spend(days=30).
Days up to ``today`` come from the recorded history, later days use ``rate_per_day``. Returns None when the horizon is
exhausted without clearing (callers ask only while K1 is in breach). Missing history days count as zero spend,
which is what the daily collector books for a day with no calls. Clock contract: ``today`` is a parameter.
"""
from datetime import date, timedelta
from typing import Dict, Optional

WINDOW_DAYS = 30


def trailing_average(history: Dict[date, float], today: date, days: int = 7) -> float:
    """Mean daily spend over the last ``days`` days including ``today`` (days without a row count as 0).
    近 days 日（含今日）的平均每日花費；沒有資料列的日子算 0。"""
    return sum(history.get(today - timedelta(days=i), 0.0) for i in range(days)) / float(days)


def _ratio_pct(window_sum: float, nav: float, monthly_subscription: float) -> float:
    return (window_sum * (365.0 / WINDOW_DAYS) + monthly_subscription * 12.0) / nav * 100.0


def project_k1_clear(history: Dict[date, float], today: date, nav: float, threshold_pct: float,
                     monthly_subscription: float, rate_per_day: float, horizon: int = 90) -> Optional[date]:
    """First day after ``today`` on which K1 is at or below ``threshold_pct``, or None within ``horizon`` days.
    今日之後 K1 首次不高於門檻的日期；horizon 天內達不到則回 None。"""
    if not nav or nav <= 0:
        raise ValueError("NAV unavailable: cannot project K1")
    for ahead in range(1, horizon + 1):
        d = today + timedelta(days=ahead)
        total = 0.0
        for back in range(WINDOW_DAYS):
            day = d - timedelta(days=back)
            total += history.get(day, 0.0) if day <= today else rate_per_day
        if _ratio_pct(total, nav, monthly_subscription) <= threshold_pct:
            return d
    return None
