import pytz
import pandas as pd
from datetime import datetime, time, timedelta
from typing import Dict, Any

try:
    import pandas_market_calendars as mcal
except ImportError:
    mcal = None

class MarketClock:
    """
    Professional Utility for US Market Hours and DST Handling.
    動態美股市場時鐘：處理夏令/冬令切換與交易所休市日。
    """
    
    def __init__(self, exchange_name: str = 'NYSE'):
        self.exchange_name = exchange_name
        self.nyse = mcal.get_calendar(exchange_name) if mcal is not None else None
        self.tz = pytz.timezone('US/Eastern')

    def is_market_open(self, buffer_minutes: int = 0) -> bool:
        """
        Check if the market is currently open.
        檢查市場目前是否開市（含緩衝時間）。
        """
        now = datetime.now(pytz.utc)
        if self.nyse is not None:
            schedule = self.nyse.schedule(start_date=now.date(), end_date=now.date())
            
            if schedule.empty:
                return False
                
            market_open = schedule.iloc[0]['market_open']
            market_close = schedule.iloc[0]['market_close']
            
            # Apply buffer if needed (e.g. for pre-market checks)
            return (market_open - pd.Timedelta(minutes=buffer_minutes)) <= now <= market_close

        # Fallback without pandas_market_calendars
        ny_now = now.astimezone(self.tz)
        if ny_now.weekday() > 4:
            return False
        open_time = ny_now.replace(hour=9, minute=30, second=0, microsecond=0) - timedelta(minutes=buffer_minutes)
        close_time = ny_now.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_time <= ny_now <= close_time

    def get_market_status(self) -> Dict[str, Any]:
        """
        Get detailed US market status including DST information.
        獲取詳細市場狀態，包含夏令時切換資訊。
        """
        now = datetime.now(self.tz)
        is_dst = now.dst().total_seconds() != 0
        
        # Get next open
        today = datetime.now(pytz.utc).date()
        if self.nyse is not None:
            schedule = self.nyse.schedule(start_date=today, end_date=pd.Timestamp(today) + pd.Timedelta(days=7))
            next_session = schedule.iloc[0]
            next_open = next_session['market_open'].isoformat()
            next_close = next_session['market_close'].isoformat()
        else:
            next_open = (now.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(days=1)).isoformat()
            next_close = (now.replace(hour=16, minute=0, second=0, microsecond=0)).isoformat()
        
        is_open = self.is_market_open()
        
        return {
            "is_open": is_open,
            "is_dst": is_dst,
            "timezone": "US/Eastern",
            "current_time": now.isoformat(),
            "next_open": next_open,
            "next_close": next_close,
            "exchange": self.exchange_name
        }

    @classmethod
    def get_nyse_time(cls) -> datetime:
        """Helper to get current time in New York."""
        return datetime.now(pytz.timezone('US/Eastern'))
